import os
from dotenv import load_dotenv
from psycopg2 import pool

# 載入 .env 檔案
load_dotenv()

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# --- Authentication & Security ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "supersecretpassword123")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "c416f5c88b770ab7fbe51fc525a1f6a1")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day

# --- Zilliz / Milvus ---
ZILLIZ_API_KEY = os.getenv("ZILLIZ_API_KEY")
CLUSTER_ENDPOINT = os.getenv("CLUSTER_ENDPOINT")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "rag6_scholarships_hybrid")

# --- PostgreSQL Database ---
DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "qa_logs2")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# 加入自訂的 API Key 用於保護 FastAPI 端點
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "supersecretapikey123")

# --- CORS ---
# 從環境變數讀取允許的來源，預設為本地開發常用的來源
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,https://tcu-scholarships-chatbot.onrender.com/")
# 將字串轉換為列表
ALLOWED_ORIGINS_LIST = [origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(',')]

# 簡單檢查以確保關鍵環境變數已設定
if not OPENAI_API_KEY or not ZILLIZ_API_KEY or not CLUSTER_ENDPOINT:
    raise ValueError("遺失關鍵環境變數： OPENAI_API_KEY, ZILLIZ_API_KEY, 或 CLUSTER_ENDPOINT 必須被設定。")

# --- Database Connection Pool ---
# 建立一個連線池，避免每次請求都重新建立連線
try:
    DB_POOL = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    print("--- [INFO] 資料庫連線池建立成功 ---")
except Exception as e:
    print(f"!!!!!! [ERROR] 資料庫連線池建立失敗: {e} !!!!!!!")
