from contextlib import contextmanager
from fastapi import HTTPException
import config
from logger import get_logger

logger = get_logger(__name__)

@contextmanager
def get_db_cursor(commit=False):
    """
    獲取資料庫連線與 cursor 的 context manager。
    若出現異常會自動復原 (rollback)，若無異常且 commit=True 則自動 commit。
    """
    if not config.DB_POOL:
        logger.error("[DB] Database connection pool is not available.")
        raise HTTPException(status_code=503, detail="Database connection pool is not available.")
    
    conn = config.DB_POOL.getconn()
    cursor = None
    try:
        cursor = conn.cursor()
        yield conn, cursor
        if commit:
            conn.commit()
    except Exception as e:
        logger.error(f"[DB] Database transaction error: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            config.DB_POOL.putconn(conn)
