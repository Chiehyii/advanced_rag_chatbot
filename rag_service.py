import time
import asyncio
from openai import AsyncOpenAI
from pymilvus import MilvusClient, AnnSearchRequest
import config
from prompts import PROMPTS
from scripts.query_analyzer import analyze_query
from sentence_transformers import CrossEncoder
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential

from logger import get_logger
from llm_service import _translate_to_zh, _rephrase_question_with_history, generate_suggested_replies
from db_repository import clean_retrieved_contexts, log_to_db

logger = get_logger(__name__)

# --- Constants ---
MIN_RERANK_SCORE = 0.2  # Minimum Cross-Encoder score to keep a document

# --- Initialize Re-Ranking Model ---
# Using a lightweight, multilingual reranker widely used for RAG (bge-reranker-base or M3)
# Note: First startup will download the model.
cross_encoder = CrossEncoder('BAAI/bge-reranker-base', max_length=512)

# --- CPU Thread Pool ---
# 限制 CPU 密集的重排序模型推論最大並發數，防止系統高負載時崩潰
cpu_executor = ThreadPoolExecutor(max_workers=2)

# 使用集中化的設定來初始化 clients
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
milvus_client = MilvusClient(
    uri=config.CLUSTER_ENDPOINT,
    token=config.ZILLIZ_API_KEY,
)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
async def get_embedding(text):
    """產生文字向量"""
    resp = await openai_client.embeddings.create(
        input=text,
        model=config.EMBEDDING_MODEL
    )
    return resp.data[0].embedding

async def retrieve_context(question: str, expr: str, lang: str = 'zh', top_k: int = 10):
    """根據問題進行混合檢索 (Dense + Sparse) + 過濾"""
    from pymilvus import AnnSearchRequest, RRFRanker

    # 1. 若使用者以英文提問，先翻成中文
    if lang == 'en':
        question_for_retrieval = await _translate_to_zh(question)
    else:
        question_for_retrieval = question

    # 2. 產生問題的向量 (Dense) — 使用原始問題
    question_dense_embedding = await get_embedding(question)

    # 3. 執行混合檢索
    dense_search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
    dense_req = AnnSearchRequest(
        data=[question_dense_embedding],
        anns_field="vector",
        param=dense_search_params,
        limit=top_k,
        expr=expr
    )

    sparse_search_params = {"metric_type": "BM25", "params": {}}
    sparse_req = AnnSearchRequest(
        data=[question_for_retrieval],  # 中文翻譯版本，BM25 才有效
        anns_field="text_sparse",
        param=sparse_search_params,
        limit=top_k,
        expr=expr
    )

    reranker = RRFRanker()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
    def _milvus_hybrid_search():
        try:
            results = milvus_client.hybrid_search(
                collection_name=config.MILVUS_COLLECTION,
                reqs=[dense_req, sparse_req],
                ranker=reranker,
                limit=top_k,
                output_fields=["id", "text", "source_file", "source_url", "identity", "category", "education_system", "tags"]
            )
            logger.info(f"[Search] Hybrid search (Dense + Sparse) succeeded.")
            return results
        except Exception as e:
            logger.warning(f"[Search] Hybrid search failed ({type(e).__name__}): {e}")
            logger.info(f"[Search] Falling back to Dense-only search.")
            try:
                results = milvus_client.search(
                    collection_name=config.MILVUS_COLLECTION,
                    data=[question_dense_embedding],
                    anns_field="vector",
                    search_params=dense_search_params,
                    limit=top_k,
                    filter=expr if expr else None,
                    output_fields=["id", "text", "source_file", "source_url", "identity", "category", "education_system", "tags"],
                )
                logger.info(f"[Search] Dense-only fallback succeeded.")
                return results
            except Exception as fallback_err:
                logger.error(f"[Search] Dense-only fallback also failed ({type(fallback_err).__name__}): {fallback_err}", exc_info=True)
                raise fallback_err

    try:
        results = await asyncio.to_thread(_milvus_hybrid_search)
    except Exception:
        results = []

    # --- Filter Fallback: 帶 filter 搜不到時，去掉 filter 重搜一次 ---
    if (not results or not results[0]) and expr:
        logger.info(f"[Filter] Filtered search returned 0 results. Retrying WITHOUT filter...")

        dense_req_no_filter = AnnSearchRequest(
            data=[question_dense_embedding],
            anns_field="vector",
            param=dense_search_params,
            limit=top_k,
            expr=""
        )
        sparse_req_no_filter = AnnSearchRequest(
            data=[question],
            anns_field="text_sparse",
            param=sparse_search_params,
            limit=top_k,
            expr=""
        )

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
        def _retry_without_filter():
            try:
                return milvus_client.hybrid_search(
                    collection_name=config.MILVUS_COLLECTION,
                    reqs=[dense_req_no_filter, sparse_req_no_filter],
                    ranker=reranker,
                    limit=top_k,
                    output_fields=["id", "text", "source_file", "source_url",
                                   "identity", "category", "education_system", "tags"]
                )
            except Exception as e:
                logger.error(f"[Filter] Retry without filter failed ({type(e).__name__}): {e}", exc_info=True)
                raise e

        try:
            results = await asyncio.to_thread(_retry_without_filter)
            if results and results[0]:
                logger.info(f"[Filter] Retry without filter found {len(results[0])} results.")
            else:
                logger.error(f"[Filter] Retry without filter also returned 0 results.")
        except Exception:
            results = []

    if not results or not results[0]:
        return []

    milvus_docs = results[0]
    
    # --- Phase 5: Cross-Encoder Re-Ranking ---
    logger.info(f"[Re-Ranking] Milvus returned {len(milvus_docs)} candidate documents. Starting Cross-Encoder scoring...")
    
    pairs = []
    for doc in milvus_docs:
        doc_text = doc.get("entity", {}).get("text", "")
        pairs.append([question_for_retrieval, doc_text])
        
    if not pairs:
        return []

    def _rank():
        return cross_encoder.predict(pairs)
        
    loop = asyncio.get_running_loop()
    scores = await loop.run_in_executor(cpu_executor, _rank)
    
    for i, doc in enumerate(milvus_docs):
        doc["cross_encoder_score"] = float(scores[i])
        
    milvus_docs.sort(key=lambda x: x["cross_encoder_score"], reverse=True)

    logger.info(f"[Re-Ranking] Candidate documents with scores (threshold={MIN_RERANK_SCORE}):")
    for rank, doc in enumerate(milvus_docs, 1):
        entity = doc.get("entity", {})
        score = doc.get("cross_encoder_score", 0.0)
        source = entity.get("source_file", "N/A")
        identity = list(entity.get("identity") or [])
        snippet = (entity.get("text") or "")[:80].replace("\n", " ")
        passed = "✓" if score >= MIN_RERANK_SCORE else "✗"
        logger.info(
            f"  [{rank}] {passed} score={score:.4f} | source={source} | "
            f"identity={identity} | text='{snippet}...'"
        )

    top_n = min(5, len(milvus_docs))
    refined_docs = [d for d in milvus_docs[:top_n] if d["cross_encoder_score"] >= MIN_RERANK_SCORE]
    
    if not refined_docs:
        top_scores = ", ".join(
            f"{d.get('entity', {}).get('source_file', 'N/A')}={d.get('cross_encoder_score', 0.0):.4f}"
            for d in milvus_docs[:top_n]
        )
        logger.info(
            f"[Re-Ranking] No documents passed the minimum score threshold ({MIN_RERANK_SCORE}). "
            f"Top-{top_n} candidate scores: [{top_scores}]"
        )
        return []
    
    logger.info(f"[Re-Ranking] Selected {len(refined_docs)} documents (threshold >= {MIN_RERANK_SCORE}). Highest score: {refined_docs[0]['cross_encoder_score']:.4f}")
    
    return refined_docs

async def generate_answer_stream(question: str, cleaned_contexts: list, lang: str = 'zh', usage_data: dict | None = None):
    """
    把清理過的 Milvus 檢索結果交給 GPT 生成自然語言回答，並以串流形式回傳。
    usage_data: 可選的字典，用於收集 streaming 結束後的 token 使用量。
    """
    from collections import defaultdict
    grouped = defaultdict(list)
    source_url_map = {}
    for c in cleaned_contexts:
        fname = c.get('source_file', '未知來源')
        grouped[fname].append(c.get('text', ''))
        if fname not in source_url_map and c.get('source_url'):
            source_url_map[fname] = c.get('source_url')

    context_for_llm = ""
    for idx, (fname, texts) in enumerate(grouped.items(), 1):
        title = fname.replace('.md', '').replace('.txt', '')
        url = source_url_map.get(fname, '')
        
        context_for_llm += f"\n---\n[文件 {idx}]\n來源名稱: {title}\n"
        if url:
            context_for_llm += f"來源網址: {url}\n"
        full_text = "\n".join(texts)
        context_for_llm += f"內容: {full_text}\n"

    system_prompt = PROMPTS[lang]['rag_system']
    user_prompt = PROMPTS[lang]['rag_user'].format(question=question, context_for_llm=context_for_llm)

    stream = await openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.usage and usage_data is not None:
            usage_data["usage"] = chunk.usage
        if chunk.choices:
            content = chunk.choices[0].delta.content or ""
            yield content

async def _handle_rag_branch(rephrased_question: str, cleaned_contexts: list, lang: str, usage_data: dict):
    logger.info(f"[RAG] RAG path: {len(cleaned_contexts)} relevant documents found.")
    context_text_for_chips = "\\n".join([c.get('text', '') for c in cleaned_contexts][:3])
    chips_task = asyncio.create_task(
        generate_suggested_replies(rephrased_question, context_text_for_chips, lang=lang)
    )

    llm_stream = generate_answer_stream(rephrased_question, cleaned_contexts, lang=lang, usage_data=usage_data)
    
    full_answer = ""
    async for chunk in llm_stream:
        full_answer += chunk
        yield {"type": "content", "data": chunk}

    unique_display_contexts = []
    seen_keys = set()
    for context in cleaned_contexts:
        unique_key = context.get('source_file')
        if unique_key and unique_key not in seen_keys:
            unique_display_contexts.append(context)
            seen_keys.add(unique_key)
    
    contexts_for_logging = unique_display_contexts
    result_data = {"contexts": unique_display_contexts}
    
    chips = await chips_task
    result_data["chips"] = chips
    
    yield {"type": "branch_done", "full_answer": full_answer, "contexts_for_logging": contexts_for_logging, "result_data": result_data}

async def _handle_small_talk_branch(rephrased_question: str, lang: str, usage_data: dict):
    logger.info(f"[Small Talk] Fallback to small talk: No relevant documents found.")
    stream = await openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=[
            {"role": "system", "content": PROMPTS[lang]['small_talk_system']},
            {"role": "user", "content": rephrased_question}
        ],
        temperature=0.7,
        stream=True,
        stream_options={"include_usage": True},
    )
    full_answer = ""
    async for chunk in stream:
        if chunk.usage:
            usage_data["usage"] = chunk.usage
        if chunk.choices:
            content = chunk.choices[0].delta.content or ""
            full_answer += content
            yield {"type": "content", "data": content}
    
    chips = await generate_suggested_replies(rephrased_question, full_answer, lang=lang)
    result_data = {"contexts": [], "chips": chips}
    yield {"type": "branch_done", "full_answer": full_answer, "contexts_for_logging": [], "result_data": result_data}

async def stream_chat_pipeline(question: str, history: list | None = None, lang: str = 'zh', title_filter: list[str] | None = None, request_id: str | None = None, session_id: str | None = None, user_id: str | None = None):
    """
    Orchestrates the entire RAG pipeline for streaming responses.
    """
    start_time = time.time()
    full_answer = ""
    original_question = question
    rephrased_question = question
    contexts_for_logging = []
    result_data = {}
    usage_data = {}
    stream_completed = False

    try:
        user_msg_count = sum(1 for msg in (history or []) if msg.get('role') == 'user')
        
        if user_msg_count > 1:
            rephrased_question = await _rephrase_question_with_history(history, question, lang=lang)
        else:
            rephrased_question = question
            logger.info("[Rephrase] Skipped rephrasing because this is the first user query.")
        
        logger.info(f"[Question] Final question: {rephrased_question} (Original: {original_question})")

        if title_filter and len(title_filter) > 0:
            intent = "scholarship"
            safe_titles = [t.replace('"', '\\"') for t in title_filter[:3]]
            title_exprs = ", ".join([f'"{t}.md"' for t in safe_titles])
            expr = f"source_file in [{title_exprs}]"
            logger.info(f"[Title Filter] User selected tags: {title_filter} → Milvus expr: {expr}")
            
            title_str = "、".join(title_filter[:3]) if lang == 'zh' else ", ".join(title_filter[:3])
            prefix = f"關於「{title_str}」：" if lang == 'zh' else f"Regarding '{title_str}': "
            rephrased_question = prefix + rephrased_question
            logger.info(f"[Title Filter] Injected tags into question: {rephrased_question}")
        else:
            try:
                intent, expr = await analyze_query(rephrased_question, lang=lang)
                logger.info(f"[Intent] Intent: {intent}, Expr(filter): {expr}")
            except Exception as analyze_err:
                logger.warning(f"[Intent] analyze_query failed ({type(analyze_err).__name__}), falling back to unfiltered RAG search.")
                intent, expr = "scholarship", ""

        cleaned_contexts = []

        if intent != 'other':
            logger.info(f"[Pipeline] Intent is '{intent}', retrieving documents (Milvus)...")
            raw_contexts = await retrieve_context(rephrased_question, expr=expr, lang=lang)
            cleaned_contexts = clean_retrieved_contexts(raw_contexts)
        else:
            logger.info(f"[Pipeline] Intent is '{intent}', skipping retrieval.")
        
        if cleaned_contexts:
            async for chunk in _handle_rag_branch(rephrased_question, cleaned_contexts, lang, usage_data):
                if chunk["type"] == "branch_done":
                    full_answer = chunk["full_answer"]
                    contexts_for_logging = chunk["contexts_for_logging"]
                    result_data = chunk["result_data"]
                else:
                    yield chunk
        else:
            async for chunk in _handle_small_talk_branch(rephrased_question, lang, usage_data):
                if chunk["type"] == "branch_done":
                    full_answer = chunk["full_answer"]
                    contexts_for_logging = chunk["contexts_for_logging"]
                    result_data = chunk["result_data"]
                else:
                    yield chunk

        stream_completed = True

    finally:
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        logger.info(f"[Total latency] {latency_ms:.2f} ms")
        
        if stream_completed:
            try:
                usage = usage_data.get("usage")
                if usage:
                    logger.info(f"[Token Usage] prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
                log_id = await asyncio.to_thread(log_to_db, original_question, rephrased_question, full_answer, contexts_for_logging, latency_ms, usage, request_id, session_id, user_id)
            except Exception as e:
                logger.error(f"[DB] log_to_db failed in thread: {e}", exc_info=True)
                log_id = None

            if log_id:
                result_data["log_id"] = log_id
        else:
            logger.warning(f"[DB] Stream did not complete (client disconnected?), skipping DB log.")
        
        yield {"type": "final_data", "data": result_data}
