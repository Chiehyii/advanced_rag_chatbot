import os
from dotenv import load_dotenv
from psycopg2 import pool
from logger import get_logger

logger = get_logger(__name__)

# 載入 .env 檔案
load_dotenv()

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# --- Authentication & Security ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not (ADMIN_PASSWORD or ADMIN_PASSWORD_HASH) or not JWT_SECRET_KEY:
    raise ValueError("Either ADMIN_PASSWORD or ADMIN_PASSWORD_HASH, and JWT_SECRET_KEY must be set in environment variables.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 7 # 7 days

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

# --- Rate Limiting ---
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "10/minute")
RATE_LIMIT_FEEDBACK = os.getenv("RATE_LIMIT_FEEDBACK", "20/minute")

# --- Notifications (LINE Messaging API) ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# --- CORS ---
# 從環境變數讀取允許的來源，預設為本地開發常用的來源
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,https://tcu-scholarships-chatbot.onrender.com/")
# 將字串轉換為列表
ALLOWED_ORIGINS_LIST = [origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(',')]

# 簡單檢查以確保關鍵環境變數已設定
if not OPENAI_API_KEY or not ZILLIZ_API_KEY or not CLUSTER_ENDPOINT:
    # 🚨 ERROR：記錄遺失關鍵環境變數
    logger.error(" 遺失關鍵環境變數： OPENAI_API_KEY, ZILLIZ_API_KEY, 或 CLUSTER_ENDPOINT 必須被設定。")
    raise ValueError("遺失關鍵環境變數： OPENAI_API_KEY, ZILLIZ_API_KEY, 或 CLUSTER_ENDPOINT 必須被設定。")

# --- Database Connection Pool ---
# 建立一個連線池，避免每次請求都重新建立連線
DB_POOL = None  # 先初始化為 None，避免連線失敗時 AttributeError
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
    # 📝 INFO：記錄資料庫連線池建立成功
    logger.info("[DB] 資料庫連線池建立成功")
except Exception as e:
    # 🚨 ERROR：記錄資料庫連線池建立失敗（DB_POOL 維持 None）
    logger.error(f"[DB] 資料庫連線池建立失敗: {e}")
