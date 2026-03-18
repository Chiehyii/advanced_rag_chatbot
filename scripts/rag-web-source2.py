import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------- 載入環境變數 -------------------------------
import os
import json
import config

# ------------------------------- 準備資料 -------------------------------
from langchain_text_splitters import RecursiveCharacterTextSplitter
from glob import glob
from openai import OpenAI
from tqdm import tqdm

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
# gemini_ef = model.dense.GeminiEmbeddingFunction(
#     model_name='gemini-embedding-001', # 指定您要的模型
#     api_key=gemini_api_key,
# )
def emb_text(text):
    return (
        openai_client.embeddings.create(input=text, model="text-embedding-3-small")
        .data[0]
        .embedding
        # gemini_ef.encode_documents([text])[0]
    )

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

data = []
doc_id = 0

for file_path in glob("milvus_docs/**/*.md", recursive=True):
    with open(file_path, "r", encoding="utf-8") as file:
        file_text = file.read()
    # text_lines = file_text.split("# ")
    # text_lines = [line.strip() for line in text_lines if line.strip()] # 過濾空白內容
    

    meta = config.get(os.path.basename(file_path), {})

    # 使用 RecursiveCharacterTextSplitter 進行切割
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_text(file_text)
    text_lines = [chunk.strip() for chunk in chunks if chunk.strip()] # 過濾空白內容

    url = meta.get("source_url", "")
    statuses = meta.get("status", [])
    edu_systems = meta.get("edu_system", [])
    subsidy_types = meta.get("subsidy_type", [])

    # 為每個文字段落加入來源資訊
    for line in tqdm(text_lines, desc=f"Processing(Creating embeddings) {os.path.basename(file_path)}"):
        data.append({
            "id": doc_id,
            "text": line,
            "source_file": os.path.basename(file_path), # 檔案名稱
            "source_path": file_path, # 完整路徑
            "source_url":url,
            "status": statuses,
            "edu_system": edu_systems,
            "subsidy_type":subsidy_types,
            "vector": emb_text(line) # 向量嵌入
        })
        doc_id += 1

print(f"總共讀取到 {len(data)} 筆文本資料")

# ------------------------------- 嵌入模型 -------------------------------


test_embedding = emb_text("Hello, world!")
embedding_dim = len(test_embedding)
print(f"Embedding維度: {embedding_dim}, 前10個值: {test_embedding[:10]} ...")

# ------------------------------- 將資料載入Milvus向量資料庫 -------------------------------

# ========建立資料========
from pymilvus import MilvusClient, DataType, connections, CollectionSchema, FieldSchema, Collection

milvus_client = MilvusClient(
                    uri=config.CLUSTER_ENDPOINT,
                    token=config.ZILLIZ_API_KEY,
                    )

# 建立 schema
schema = milvus_client.create_schema(
    auto_id=False,
    enable_dynamic_field=True
)

collection_name = config.MILVUS_COLLECTION

schema.add_field("id", DataType.INT64, is_primary=True)
schema.add_field("text", DataType.VARCHAR, max_length=10000)
schema.add_field("source_file", DataType.VARCHAR, max_length=256)
schema.add_field("source_path", DataType.VARCHAR, max_length=2048)
schema.add_field("source_url", DataType.VARCHAR, max_length=200)
schema.add_field("status", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
schema.add_field("edu_system", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
schema.add_field("subsidy_type", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
schema.add_field("vector", DataType.FLOAT_VECTOR, dim=1536)

# 若 collection 已存在則刪除
if milvus_client.has_collection(collection_name):
    milvus_client.drop_collection(collection_name)

# 創建 collection
milvus_client.create_collection(
    collection_name=collection_name,
    schema=schema,
    consistency_level="Bounded"
)

# ========插入資料========
insert_result = milvus_client.insert(collection_name=collection_name, data=data)
print(f"插入結果: {insert_result}")

# ------------------------------- 修正後的流程 -------------------------------

# 1. 為 vector 欄位建立索引 (必須在 load 之前)
print("正在為 vector 欄位建立索引...")
index_params = milvus_client.prepare_index_params()

# 為名為 "vector" 的欄位新增索引
index_params.add_index(
    field_name="vector",
    index_type="AUTOINDEX",  # 讓 Milvus 自動選擇最佳索引類型
    metric_type="COSINE"      # 設定向量距離的計算方式，L2 (歐氏距離) 是最常用的
)

milvus_client.create_index(
    collection_name=collection_name,
    index_params=index_params
    
)
print("索引建立完成。")

# 2. 載入集合至記憶體 (現在可以成功了)
print("正在將集合加載到記憶體...")
milvus_client.load_collection(collection_name=collection_name)
print("集合已成功載入到記憶體。")

# 3. 驗證資料是否已存在且可查詢
stats = milvus_client.get_collection_stats(collection_name=collection_name)
print(f"\n集合 '{collection_name}' 的統計資訊: {stats}")

# 執行一個簡單的查詢來確認資料可讀取
query_res = milvus_client.query(
    collection_name=collection_name,
    filter='array_contains(status, "原住民") and array_contains(edu_system, "大學部")',
    output_fields=["id", "source_file"]
)
print(f"\n執行查詢驗證，成功取回 {len(query_res)} 筆資料:")
print(query_res)