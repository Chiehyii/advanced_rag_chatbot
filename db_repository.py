import json
import config
from db import get_db_cursor
from logger import get_logger

logger = get_logger(__name__)

def clean_retrieved_contexts(retrieved_docs: list):
    """
    [CODE-3] 將檢索結果記錄到日誌系統，並回傳一個清理過的、可序列化的列表。
    """
    if not retrieved_docs:
        logger.info("[RAG] No documents retrieved.")
        return []

    cleaned_contexts = []
    for i, res in enumerate(retrieved_docs, 1):
        entity = res.get("entity", {})
        score = res.get("cross_encoder_score", res.get("distance", 0.0))

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
    try:
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None

        insert_query = f"""INSERT INTO {config.DB_TABLE_NAME} 
                         (question, rephrased_question, answer, retrieved_contexts, latency_ms, prompt_tokens, completion_tokens, total_tokens)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;"""
        
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(insert_query, (
                question, rephrased_question, answer, 
                json.dumps(contexts, ensure_ascii=False), 
                latency_ms, prompt_tokens, completion_tokens, total_tokens
            ))
            log_id = cursor.fetchone()[0]
            
        logger.info(f"[DB] Successfully wrote question to PostgreSQL database, ID: {log_id}.")
        return log_id
    except Exception as e:
        logger.error(f"[DB] Failed to write to PostgreSQL database: {e}", exc_info=True)
        return None
