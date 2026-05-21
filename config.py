import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from psycopg2 import pool
from logger import get_logger

logger = get_logger(__name__)

# 載入 .env 檔案
load_dotenv()


def _parse_int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value such as true or false.")


def _validate_runtime_config():
    errors = []
    warnings = []

    if not ADMIN_USERNAME:
        errors.append("ADMIN_USERNAME must be set.")
    if not (ADMIN_PASSWORD or ADMIN_PASSWORD_HASH):
        errors.append("Either ADMIN_PASSWORD or ADMIN_PASSWORD_HASH must be set.")
    if ENVIRONMENT == "production" and not ADMIN_PASSWORD_HASH:
        errors.append("ADMIN_PASSWORD_HASH must be set in production. Plain ADMIN_PASSWORD is not accepted.")
    if not JWT_SECRET_KEY:
        errors.append("JWT_SECRET_KEY must be set.")
    elif ENVIRONMENT == "production" and len(JWT_SECRET_KEY) < 32:
        errors.append("JWT_SECRET_KEY must be at least 32 characters in production.")
    if DB_POOL_MINCONN > DB_POOL_MAXCONN:
        errors.append("DB_POOL_MINCONN must be less than or equal to DB_POOL_MAXCONN.")
    if RATE_LIMIT_STORAGE_URI:
        parsed_rate_limit_uri = urlparse(RATE_LIMIT_STORAGE_URI)
        if parsed_rate_limit_uri.scheme not in {"redis", "rediss"}:
            errors.append("RATE_LIMIT_STORAGE_URI must start with redis:// or rediss://.")
    if "*" in ALLOWED_ORIGINS_LIST:
        errors.append("CORS_ALLOWED_ORIGINS cannot contain * when credentials are enabled.")
    if ENVIRONMENT == "production":
        insecure_origins = [
            origin for origin in ALLOWED_ORIGINS_LIST
            if origin.startswith("http://") and "localhost" not in origin and "127.0.0.1" not in origin
        ]
        if insecure_origins:
            errors.append("Production CORS origins must use HTTPS unless they are localhost.")
    if not RATE_LIMIT_STORAGE_URI:
        warnings.append("RATE_LIMIT_STORAGE_URI is not set; rate limits are per process.")

    for warning in warnings:
        logger.warning(f"[Config] {warning}")
    if errors:
        raise ValueError("Invalid runtime configuration: " + " ".join(errors))


# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# --- Authentication & Security ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = _parse_int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 15, minimum=1)
REFRESH_TOKEN_EXPIRE_DAYS = 7 # 7 days

# --- Zilliz / Milvus ---
ZILLIZ_API_KEY = os.getenv("ZILLIZ_API_KEY")
CLUSTER_ENDPOINT = os.getenv("CLUSTER_ENDPOINT")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "tcuscholarships_milvus")

# --- PostgreSQL Database ---
DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "qa_logs2")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_POOL_MINCONN = _parse_int_env("DB_POOL_MINCONN", 1, minimum=1)
DB_POOL_MAXCONN = _parse_int_env("DB_POOL_MAXCONN", 10, minimum=1)

# --- Rate Limiting ---
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "10/minute")
RATE_LIMIT_FEEDBACK = os.getenv("RATE_LIMIT_FEEDBACK", "20/minute")
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "").strip() or None

# --- Notifications (LINE Messaging API) ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# --- Environment ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
TRUST_PROXY_HEADERS = _parse_bool_env("TRUST_PROXY_HEADERS", False)
MAX_REQUEST_BODY_BYTES = _parse_int_env("MAX_REQUEST_BODY_BYTES", 1 * 1024 * 1024, minimum=1024)
CHECKPOINT_RETENTION_DAYS = _parse_int_env("CHECKPOINT_RETENTION_DAYS", 7, minimum=1)
QA_LOG_RETENTION_DAYS = _parse_int_env("QA_LOG_RETENTION_DAYS", 90, minimum=1)
SCHEDULER_LOCKS_ENABLED = _parse_bool_env("SCHEDULER_LOCKS_ENABLED", True)
ENABLE_WEB_SCHEDULER = _parse_bool_env("ENABLE_WEB_SCHEDULER", True)

# --- CORS ---
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,https://tcu-scholarships-chatbot.onrender.com")
# Strip trailing slashes — mismatched origins (e.g. "https://example.com/") silently break CORS
ALLOWED_ORIGINS_LIST = [origin.strip().rstrip('/') for origin in CORS_ALLOWED_ORIGINS.split(',') if origin.strip()]

_validate_runtime_config()

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
        minconn=DB_POOL_MINCONN,
        maxconn=DB_POOL_MAXCONN,
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
