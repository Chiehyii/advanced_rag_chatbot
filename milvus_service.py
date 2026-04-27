import uuid
from pymilvus import MilvusClient, DataType, Function, FunctionType
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
import config
from logger import get_logger

logger = get_logger(__name__)

# Reusing the existing OpenAI client setup from admin_api
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

def emb_text(text: str):
    return (
        openai_client.embeddings.create(input=text, model=config.EMBEDDING_MODEL)
        .data[0]
        .embedding
    )

def emb_texts_batch(texts: list[str]) -> list[list[float]]:
    """[PERF-1] 批次嵌入：一次 API 呼叫取得所有 chunk 的向量，大幅減少等待時間。"""
    if not texts:
        return []
    response = openai_client.embeddings.create(input=texts, model=config.EMBEDDING_MODEL)
    return [item.embedding for item in response.data]

def _insert_chunks_to_milvus(
    milvus_client,
    collection_name: str,
    markdown_content: str,
    title: str,
    scholarship_code: str,
    link: str,
    identity: list,
    education_system: list,
    category: str,
    tags: list,
) -> int:
    """
    [CODE-1] 抽取的共用函式——切分、批次嵌入、寫入 Milvus。
    save 和 update 都呼叫這鄿，不再重複相同的逻輯。
    回傳實際插入的 chunk 數量。
    """
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = [c.strip() for c in text_splitter.split_text(markdown_content) if c.strip()]
    if not chunks:
        return 0

    # [PERF-1] 批次嵌入
    vectors = emb_texts_batch(chunks)

    data_to_insert = []
    for chunk, vector in zip(chunks, vectors):
        data_to_insert.append({
            # [CODE-2] 使用 UUID 確保唯一性，取代有潜在碰撞風險的 random.randint
            "id": uuid.uuid4().int >> 65, # 右移 65 位確保結果 ≤ 2^63-1（Milvus INT64 上限）但如果數據預計會超過 1,000 萬筆 id可能會有重複的風險，建議使用 uuid.uuid4().int >> 64並重建milvus collection id 欄位= varchar
            "text": chunk,
            "source_file": title + ".md",
            "source_path": scholarship_code,
            "source_url": link or "",
            "identity": identity,
            "education_system": education_system,
            "category": [category] if category else [],
            "tags": tags,
            "vector": vector
        })

    if data_to_insert:
        milvus_client.insert(collection_name=collection_name, data=data_to_insert)
        milvus_client.flush(collection_name=collection_name)

    return len(data_to_insert)

def init_milvus_collection():
    """Initializes the collection if it doesn't exist, similar to rag-web-source2-hybrid.py"""
    milvus_client = MilvusClient(
        uri=config.CLUSTER_ENDPOINT,
        token=config.ZILLIZ_API_KEY,
    )
    collection_name = config.MILVUS_COLLECTION

    if milvus_client.has_collection(collection_name):
        return milvus_client, collection_name

    logger.info(f"[Admin API] Collection {collection_name} non-existent, creating it...")
    schema = milvus_client.create_schema(
        auto_id=False,
        enable_dynamic_field=True
    )
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("text", DataType.VARCHAR, max_length=5000, enable_analyzer=True)
    schema.add_field("source_file", DataType.VARCHAR, max_length=256)
    schema.add_field("source_path", DataType.VARCHAR, max_length=2048)
    schema.add_field("source_url", DataType.VARCHAR, max_length=2048)  # [CODE-5] 專這个字段將 200 展小為 2048，与 source_path 一致，支援較長的 URL
    schema.add_field("identity", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("education_system", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("category", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("tags", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=1536)
    schema.add_field("text_sparse", DataType.SPARSE_FLOAT_VECTOR, description="Sparse vector")

    bm25_function = Function(
        name="text_bm25_emb",
        input_field_names=["text"],
        output_field_names=["text_sparse"],
        function_type=FunctionType.BM25,
    )
    schema.add_function(bm25_function)

    milvus_client.create_collection(
        collection_name=collection_name,
        schema=schema,
        consistency_level="Bounded"
    )

    index_params = milvus_client.prepare_index_params()
    index_params.add_index(
        field_name="vector", index_name="vector_index", 
        index_type="AUTOINDEX", metric_type="COSINE"
    )
    index_params.add_index(
        field_name="text_sparse", index_name="text_sparse_index",
        index_type="SPARSE_INVERTED_INDEX", metric_type="BM25",
        params={"inverted_index_algo": "DAAT_MAXSCORE"}
    )
    milvus_client.create_index(collection_name=collection_name, index_params=index_params)
    milvus_client.load_collection(collection_name=collection_name)
    
    return milvus_client, collection_name
