import sys
import psycopg2
import time
import json
import asyncio
from pydantic import BaseModel

from openai import AsyncOpenAI
from pymilvus import MilvusClient

# 匯入集中化的設定
import config
from prompts import PROMPTS

from scripts.self_query import generate_milvus_expr
from sentence_transformers import CrossEncoder

# 意圖分類
from scripts.intent_classification import intent_classification

# 引入 logger
from logger import get_logger
logger = get_logger(__name__)

# --- Constants ---
MIN_RERANK_SCORE = 0.3  # Minimum Cross-Encoder score to keep a document

# --- Initialize Re-Ranking Model ---
# Using a lightweight, multilingual reranker widely used for RAG (bge-reranker-base or M3)
# Note: First startup will download the model.
cross_encoder = CrossEncoder('BAAI/bge-reranker-base', max_length=512)

# 使用集中化的設定來初始化 clients
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
milvus_client = MilvusClient(
    uri=config.CLUSTER_ENDPOINT,
    token=config.ZILLIZ_API_KEY,
)

async def get_embedding(text):
    """產生文字向量"""
    resp = await openai_client.embeddings.create(
        input=text,
        model=config.EMBEDDING_MODEL
    )
    return resp.data[0].embedding

async def retrieve_context(question: str, lang: str = 'zh', top_k: int = 20):
    """根據問題進行混合檢索 (Dense + Sparse) + 過濾"""
    from pymilvus import AnnSearchRequest, RRFRanker

    # 1. 產生問題的向量 (Dense)
    question_dense_embedding = await get_embedding(question)

    # 2. 產生問題的向量 (Sparse) - 使用 Server-side BM25 Function
    # 直接將問題文字傳送給 sparse field，Server 端會自動透過 Function 生成 Sparse Vector
    
    # 2. 透過 LLM 動態提取 metadata 過濾條件 (Self-Querying)
    expr = await generate_milvus_expr(question)
    # 📝 INFO：記錄動態提取的 Milvus 查詢條件
    logger.info(f"[Self-Query] Milvus Dynamic Expr: '{expr}'")

    # 3. 執行混合檢索
    # Dense Request
    dense_search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
    dense_req = AnnSearchRequest(
        data=[question_dense_embedding],
        anns_field="vector",
        param=dense_search_params,
        limit=top_k,
        expr=expr
    )

    # Sparse Request (Server-side BM25)
    sparse_search_params = {"metric_type": "BM25", "params": {}} 
    sparse_req = AnnSearchRequest(
        data=[question], # 直接傳文字，依賴 Server-side Function 轉換
        anns_field="text_sparse",
        param=sparse_search_params,
        limit=top_k,
        expr=expr
    )

    # Reranker
    reranker = RRFRanker()

    def _milvus_hybrid_search():
        try:
            # 嘗試 Hybrid Search (Dense + Sparse BM25)
            results = milvus_client.hybrid_search(
                collection_name=config.MILVUS_COLLECTION,
                reqs=[dense_req, sparse_req],
                ranker=reranker,
                limit=top_k,
                output_fields=["id", "text", "source_file", "source_url", "identity", "category", "education_system", "tags"]
            )
            # 📝 INFO：記錄混合檢索成功
            logger.info(f"[Search] Hybrid search (Dense + Sparse) succeeded.")
            return results
        except Exception as e:
            # ⚠️ WARNING：因為系統有 Fallback 備案不會當機，所以這裡只做記錄，不拋出錯誤。
            logger.warning(f"[Search] Hybrid search failed ({type(e).__name__}): {e}")
            # 📝 INFO：記錄改用純向量檢索
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
                # 📝 INFO：記錄純向量檢索成功
                logger.info(f"[Search] Dense-only fallback succeeded.")
                return results
            except Exception as fallback_err:
                # 🚨 ERROR：純向量檢索也失敗 (連備案都失敗了，那就是嚴重的錯誤)
                logger.error(f"[Search] Dense-only fallback also failed ({type(fallback_err).__name__}): {fallback_err}", exc_info=True)
                return []

    results = await asyncio.to_thread(_milvus_hybrid_search)

    # --- Filter Fallback: 帶 filter 搜不到時，去掉 filter 重搜一次 ---
    if (not results or not results[0]) and expr:
        # 📝 INFO：記錄帶 filter 搜不到，去掉 filter 重搜 (因為沒搜到東西而放寬條件)
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
                # 🚨 ERROR：重試發生異常，去掉 filter 重搜也失敗
                logger.error(f"[Filter] Retry without filter failed ({type(e).__name__}): {e}", exc_info=True)
                return []

        results = await asyncio.to_thread(_retry_without_filter)
        if results and results[0]:
            # 📝 INFO：記錄去掉 filter 重搜成功
            logger.info(f"[Filter] Retry without filter found {len(results[0])} results.")
        else:
            # 🚨 ERROR：去掉 filter 重搜也失敗 (連備案都失敗了，那就是嚴重的錯誤)
            logger.error(f"[Filter] Retry without filter also returned 0 results.")

    if not results or not results[0]:
        return []

    milvus_docs = results[0]
    
    # --- Phase 5: Cross-Encoder Re-Ranking ---
    # 📝 INFO：記錄 Cross-Encoder Re-Ranking
    logger.info(f"[Re-Ranking] Milvus returned {len(milvus_docs)} candidate documents. Starting Cross-Encoder scoring...")
    
    # Prepare pairs for scoring: (question, document_text)
    pairs = []
    for doc in milvus_docs:
        doc_text = doc.get("entity", {}).get("text", "")
        pairs.append([question, doc_text])
        
    if not pairs:
        return []

    # Run predictions in a thread since model inference is blocking
    def _rank():
        return cross_encoder.predict(pairs)
        
    scores = await asyncio.to_thread(_rank)
    
    # Attach scores to documents and sort descending
    for i, doc in enumerate(milvus_docs):
        doc["cross_encoder_score"] = float(scores[i])
        
    milvus_docs.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    
    # Pick the Top 5 most relevant, then filter by minimum score threshold
    top_n = min(5, len(milvus_docs))
    refined_docs = [d for d in milvus_docs[:top_n] if d["cross_encoder_score"] >= MIN_RERANK_SCORE]
    
    if not refined_docs:
        # 📝 INFO：記錄 Cross-Encoder Re-Ranking 失敗
        logger.info(f"[Re-Ranking] No documents passed the minimum score threshold ({MIN_RERANK_SCORE}).")
        return []
    
    # 📝 INFO：記錄 Cross-Encoder Re-Ranking 成功
    logger.info(f"[Re-Ranking] Selected {len(refined_docs)} documents (threshold >= {MIN_RERANK_SCORE}). Highest score: {refined_docs[0]['cross_encoder_score']:.4f}")
    
    return refined_docs

def log_and_clean_contexts(retrieved_docs: list):
    """
    將檢索結果打印到控制台，並返回一個清理過的、可序列化的列表。
    """
    print("\n=== RAG檢索結果 ===")
    if not retrieved_docs:
        # 📝 INFO：記錄檢索結果為空
        logger.info("[RAG] No documents retrieved.")
        # print("（沒有檢索到任何結果）")
        return []

    cleaned_contexts = []
    for i, res in enumerate(retrieved_docs, 1):
        entity = res.get("entity", {})
        
        # fallback to distance if score isn't present
        score = res.get("cross_encoder_score", res.get("distance", 0.0))
        
        # 📝 INFO：記錄檢索結果
        # logger.info(f"[RAG] Retrieved document {i}: {entity.get('text', '')[:100]}... (Score: {score:.4f}, Source: {entity.get('source_file', 'N/A')})")
        # print(f"結果 {i}:")
        # print(f"內容: {entity.get('text', '')[:100]}...")
        # print(f"相似度: {score:.4f}, 來源: {entity.get('source_file', 'N/A')}")
        # print("-" * 50)

        identity = entity.get("identity")
        category = entity.get("category")
        education_system = entity.get("education_system")
        tags = entity.get("tags")

        cleaned_contexts.append({
            "id": res.get("id"),
            "text": entity.get("text"),
            "source_file": entity.get("source_file", "").replace(".md", ""),
            "source_url": entity.get("source_url"),
            "identity": list(identity) if identity else [],
            "category": list(category) if category else [],
            "education_system": list(education_system) if education_system else [],
            "tags": list(tags) if tags else [],
            "distance": score  # 繼續使用 distance 鍵名以相容先前的 DB schema 與前端
        })
    return cleaned_contexts

def log_to_db(question, rephrased_question, answer, contexts, latency_ms, usage):
    """將問答資料和 token 使用量記錄到 PostgreSQL 資料庫中"""

    # 檢查有沒有連線池可以用
    if not config.DB_POOL:
        # 🚨 ERROR：找不到資料庫連線池
        logger.error("[DB] No database connection pool available.")
        return None

    # 1. 從連線池借用一個連線
    conn = config.DB_POOL.getconn()
    cursor = None
    try:
        cursor = conn.cursor()
        
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None

        insert_query = f"""INSERT INTO {config.DB_TABLE_NAME} 
                         (question, rephrased_question, answer, retrieved_contexts, latency_ms, prompt_tokens, completion_tokens, total_tokens)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;"""
        
        cursor.execute(insert_query, (question, rephrased_question, answer, json.dumps(contexts, ensure_ascii=False), latency_ms, prompt_tokens, completion_tokens, total_tokens))
        log_id = cursor.fetchone()[0]
        conn.commit()
        # 📝 INFO：記錄資料庫寫入成功
        logger.info(f"[DB] Successfully wrote question to PostgreSQL database, ID: {log_id}.")
        return log_id
    except psycopg2.Error as e:
        # 發生錯誤時要復原(Rollback)
        if conn: conn.rollback()
        # 🚨 ERROR：資料庫寫入錯誤
        logger.error(f"[DB] Failed to write to PostgreSQL database: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        # 2. 用完要把連線還給連線池
        if conn: config.DB_POOL.putconn(conn)

async def _rephrase_question_with_history(history: list, question: str, lang: str = 'zh') -> str:
    """
    使用對話歷史來重構一個新的、獨立的問題。
    """
    if not history:
        return question

    history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-8:]])
    system_prompt = PROMPTS[lang]['rephrase_system']
    user_prompt = PROMPTS[lang]['rephrase_user'].format(history_str=history_str, question=question)

    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=150,
        )
        rephrased_question = response.choices[0].message.content.strip()
        if not rephrased_question:
            return question
        # 📝 INFO：記錄問題重構成功
        logger.info(f"[Rephrase] Successfully rephrased question: {rephrased_question}")
        return rephrased_question
    except Exception as e:
        # ⚠️ WARNING：問題重構失敗
        logger.warning(f"[Rephrase] Failed to rephrase question: {e}", exc_info=True)
        return question

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
    for fname, texts in grouped.items():
        title = fname.replace('.md', '').replace('.txt', '')
        url = source_url_map.get(fname, '')
        context_for_llm += f"\n---\n來源名稱: {title}\n"
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
        # The final chunk has usage data but empty choices
        if chunk.usage and usage_data is not None:
            usage_data["usage"] = chunk.usage
        if chunk.choices:
            content = chunk.choices[0].delta.content or ""
            yield content

class SuggestedReplies(BaseModel):
    replies: list[str]

async def generate_suggested_replies(question: str, answer: str, lang: str = 'zh') -> list[str]:
    system_prompt = (
        "You are a helpful assistant predicting the user's next questions. Rules:\n"
        "1. Generate exactly 3 short follow-up questions (under 15 words each).\n"
        "2. If the answer mentions specific scholarships, the questions MUST target those specific scholarships by name (e.g., 'What is the exact deadline for Scholarship X?').\n"
        "3. DO NOT generate broad or generic questions.\n"
        "4. CRITICAL: DO NOT ask about any information that was already provided in the answer.\n"
        "5. CRITICAL: DO NOT ask questions that the bot cannot answer, such as asking for someone's personal email, direct phone number, or physical office address."
    )
    if lang == 'zh':
        system_prompt = (
            "你是一個預測使用者意圖的貼心助教。請根據使用者的問題以及你的完整回答，產生 3 個使用者接下來最可能追問的「短問題」。\n"
            "【嚴格規則】\n"
            "1. 每個問題必須極度簡短且口語（15字以內）。\n"
            "2. 如果你的回答中提到了多項獎學金，請**挑其中一個最有代表性的獎學金**名稱來發問（例如：「ＯＯ獎學金的申請表在哪裡下載？」），絕對不要問籠統廣泛的問題（例如：「有哪些推薦的獎學金？」）。\n"
            "3. **絕對不可以**問回答中「已經提供過的資訊」。\n"
            "4. **絕對不可以**問「機器人無法回答的問題」，例如：承辦人的信箱是什麼？全球處的地址在哪裡？聯絡電話是幾號？（因為隱私關係，知識庫通常缺乏這些聯絡細節）。\n"
            "5. 建議詢問：該獎學金的應備文件、申請資格細節、或是截止日期（如果回答中尚未提及）。"
        )
    
    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User: {question}\n\nAssistant: {answer}"}
            ],
            response_format=SuggestedReplies,
            temperature=0.7,
        )
        return response.choices[0].message.parsed.replies
    except Exception as e:
        # ⚠️ WARNING：根據使用者的問答預測產生的3個問題失敗了
        logger.warning(f"[Rephrase] Failed to predict follow-up questions: {e}", exc_info=True)
        return []

async def stream_chat_pipeline(question: str, history: list | None = None, lang: str = 'zh'):
    """
    Orchestrates the entire RAG pipeline for streaming responses.
    """
    start_time = time.time()
    full_answer = ""
    original_question = question
    rephrased_question = question
    contexts_for_logging = []
    result_data = {}
    usage_data = {}  # Mutable container to capture streaming token usage

    try:
        if history:
            rephrased_question = await _rephrase_question_with_history(history, question, lang=lang)
        
        # 📝 INFO：記錄最終問題
        logger.info(f"[Question] Final question: {rephrased_question} (Original: {original_question})")

        # --- 1. 先判斷意圖：決定是否需要動用資料庫 ---
        intent = await intent_classification(rephrased_question, lang=lang)
        # 📝 INFO：記錄辨識意圖
        logger.info(f"[Intent] Intent: {intent}")

        cleaned_contexts = [] # 預設為空列表

        # 如果意圖不是 'other' 就去資料庫翻找資料
        if intent != 'other':
            print(f"[Pipeline] Intent is '{intent}', retrieving documents...")
            raw_contexts = await retrieve_context(rephrased_question, lang=lang)
            cleaned_contexts = log_and_clean_contexts(raw_contexts)
        else:
            print(f"[Pipeline] Intent is '{intent}', skipping retrieval.")
        
        # ---2. 根據是否找到文件決定要走 RAG 還是 Small Talk ---
        if cleaned_contexts:
            # --- RAG path: we have relevant documents ---
            # 📝 INFO：記錄找到的文件數量
            logger.info(f"[RAG] RAG path: {len(cleaned_contexts)} relevant documents found.")

            llm_stream = generate_answer_stream(rephrased_question, cleaned_contexts, lang=lang, usage_data=usage_data)
            buffer = ""
            delimiter = "|||SOURCES|||"

            async for chunk in llm_stream:
                full_answer += chunk
                buffer += chunk

                if delimiter in buffer:
                    answer_part, _ = buffer.split(delimiter, 1)
                    yield {"type": "content", "data": answer_part}
                    async for remaining_chunk in llm_stream:
                        full_answer += remaining_chunk
                    break
                else:
                    if len(buffer) > len(delimiter):
                        yield_part = buffer[:-len(delimiter)]
                        yield {"type": "content", "data": yield_part}
                        buffer = buffer[-len(delimiter):]
            else:
                if buffer:
                    yield {"type": "content", "data": buffer}

            answer_part = full_answer
            cited_source_names = []
            if "|||SOURCES|||" in full_answer:
                parts = full_answer.split("|||SOURCES|||")
                answer_part = parts[0].strip()
                source_names_str = parts[1].strip()
                if source_names_str:
                    cited_source_names = [name.strip() for name in source_names_str.split(',')]
            
            full_answer = answer_part

            cited_source_names_set = set(cited_source_names)
            all_cited_contexts = [ctx for ctx in cleaned_contexts if ctx.get('source_file') in cited_source_names_set]
            contexts_for_logging = all_cited_contexts

            unique_display_contexts = []
            seen_keys = set()
            for context in all_cited_contexts:
                unique_key = context.get('source_file')
                if unique_key and unique_key not in seen_keys:
                    unique_display_contexts.append(context)
                    seen_keys.add(unique_key)
            
            result_data = {"contexts": unique_display_contexts}
            
            # Predict next questions
            chips = await generate_suggested_replies(rephrased_question, full_answer, lang=lang)
            result_data["chips"] = chips
        
        else:
            # --- Fallback: No relevant documents found, use small talk ---
            # 📝 INFO：記錄使用小對話
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
            async for chunk in stream:
                if chunk.usage:
                    usage_data["usage"] = chunk.usage
                if chunk.choices:
                    content = chunk.choices[0].delta.content or ""
                    full_answer += content
                    yield {"type": "content", "data": content}
            
            chips = await generate_suggested_replies(rephrased_question, full_answer, lang=lang)
            result_data = {"contexts": [], "chips": chips}

    finally:
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        # 📝 INFO：記錄總耗時
        logger.info(f"[Total latency] {latency_ms:.2f} ms")
        
        try:
            usage = usage_data.get("usage")
            if usage:
                # 📝 INFO：記錄 Token 使用量
                logger.info(f"[Token Usage] prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
            log_id = await asyncio.to_thread(log_to_db, original_question, rephrased_question, full_answer, contexts_for_logging, latency_ms, usage)
        except Exception as e:
            # 🚨 ERROR：寫入資料庫失敗
            logger.error(f"[DB] log_to_db failed in thread: {e}", exc_info=True)
            log_id = None

        if log_id:
            result_data["log_id"] = log_id
        
        yield {"type": "final_data", "data": result_data}
