import hashlib
import json
import asyncio
import os
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
import config
from db import get_db_cursor
from utils import FetchSSLError, UnsafeUrlError, safe_fetch_text_async
from logger import get_logger
from psycopg2 import sql as pg_sql
from notifier import send_line_message
from prompts import PROMPTS
from admin_api import openai_client
from milvus_service import init_milvus_collection, emb_texts_batch
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = get_logger(__name__)

EXTRACTION_MAX_COMPLETION_TOKENS = int(os.getenv("EXTRACTION_MAX_COMPLETION_TOKENS", "4000"))
EXTRACTION_RETRY_MAX_COMPLETION_TOKENS = int(os.getenv("EXTRACTION_RETRY_MAX_COMPLETION_TOKENS", "6000"))
CHECKPOINT_CLEANUP_INTERVAL_HOURS = int(os.getenv("CHECKPOINT_CLEANUP_INTERVAL_HOURS", "24"))
SCHOLARSHIP_INSPECTION_LOCK_ID = 771001
CHECKPOINT_CLEANUP_LOCK_ID = 771002
QA_LOG_CLEANUP_LOCK_ID = 771003


def _run_with_advisory_lock(lock_id: int, job_name: str, func, *args, **kwargs):
    """Run one scheduler job at a time across Uvicorn workers/instances."""
    if not getattr(config, "SCHEDULER_LOCKS_ENABLED", True):
        return func(*args, **kwargs)

    if not config.DB_POOL:
        logger.warning(f"[Scheduler] DB pool unavailable; running {job_name} without advisory lock.")
        return func(*args, **kwargs)

    conn = None
    cursor = None
    locked = False
    try:
        conn = config.DB_POOL.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s);", (lock_id,))
        locked = bool(cursor.fetchone()[0])
        if not locked:
            logger.info(f"[Scheduler] Skipping {job_name}; another worker holds the advisory lock.")
            return None

        logger.info(f"[Scheduler] Acquired advisory lock for {job_name}.")
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"[Scheduler] Failed while running locked job {job_name}: {e}", exc_info=True)
        return None
    finally:
        if cursor:
            try:
                if locked:
                    cursor.execute("SELECT pg_advisory_unlock(%s);", (lock_id,))
            except Exception as e:
                logger.warning(f"[Scheduler] Failed to release advisory lock for {job_name}: {e}")
            cursor.close()
        if conn:
            config.DB_POOL.putconn(conn)


def run_inspection_once():
    return _run_with_advisory_lock(
        SCHOLARSHIP_INSPECTION_LOCK_ID,
        "scholarship_inspection",
        run_inspection,
    )


def cleanup_langgraph_checkpoints_once():
    return _run_with_advisory_lock(
        CHECKPOINT_CLEANUP_LOCK_ID,
        "langgraph_checkpoint_cleanup",
        cleanup_langgraph_checkpoints,
    )


def cleanup_qa_logs_once():
    return _run_with_advisory_lock(
        QA_LOG_CLEANUP_LOCK_ID,
        "qa_log_cleanup",
        cleanup_qa_logs,
    )


def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

async def _fetch_url_text(url: str) -> str:
    try:
        content = await safe_fetch_text_async(url, timeout=15)
        soup = BeautifulSoup(content, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    except UnsafeUrlError as e:
        logger.warning(f"[Scheduler] Unsafe URL blocked: {url} ({e})")
        return ""
    except FetchSSLError as e:
        logger.warning(f"[Scheduler] SSL verification failed: {url} ({e})")
        return ""
    except ValueError as e:
        logger.warning(f"[Scheduler] Fetch rejected: {url} ({e})")
        return ""
    except Exception as e:
        logger.warning(f"[Scheduler] Failed to scrape {url}: {type(e).__name__} - {e}")
        try:
            from notifier import send_line_message
            send_line_message(f"⚠️ [系統通知] 爬蟲報錯\n網址: {url}\n錯誤: {type(e).__name__} - {e}")
        except Exception:
            pass
        return ""

async def _async_run_inspection(rows):
    scraped_results = []
    
    # 限制最大並發數為 10
    sem = asyncio.Semaphore(10)
    
    async def fetch_row(row):
        scholarship_code, title, url, old_hash = row
        async with sem:
            latest_text = await _fetch_url_text(url)
        return row, latest_text
    
    tasks = [fetch_row(row) for row in rows]
    # 並發執行，某個失敗不會中斷全域
    results = await asyncio.gather(*tasks, return_exceptions=True)
        
    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"[Scheduler] Scrape error during gather: {res}")
        else:
            scraped_results.append(res)
            
    return scraped_results

def _parse_extraction_json(raw_content: str, url: str, finish_reason: str | None, attempt: int) -> dict:
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.warning(
            "[Scheduler] AI extraction returned invalid JSON for %s "
            "(attempt=%s, finish_reason=%s, chars=%s): %s",
            url,
            attempt,
            finish_reason,
            len(raw_content or ""),
            e,
        )
        return {}

    if not isinstance(parsed, dict):
        logger.warning(f"[Scheduler] AI extraction returned non-object JSON for {url}: {type(parsed).__name__}")
        return {}
    return parsed


def _call_extraction_model(messages: list[dict], max_completion_tokens: int):
    response = openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        # reasoning_effort="minimal",
        response_format={"type": "json_object"},
    )
    choice = response.choices[0]
    return choice.message.content or "", getattr(choice, "finish_reason", None)


def ask_ai_to_extract(url: str, content: str) -> dict:
    system_prompt = PROMPTS['zh']['extraction_system']
    safe_content = content[:8000] if content else ""
    base_user_prompt = (
        f"URL: {url}\n\n"
        "請只回傳一個合法 JSON object，不要使用 Markdown code block。"
        "所有字串內的換行必須正確跳脫，markdown_content 請控制在 4000 字以內。\n\n"
        "Content:\n"
        + safe_content
    )

    attempts = [
        (
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": base_user_prompt},
            ],
            EXTRACTION_MAX_COMPLETION_TOKENS,
        ),
        (
            [
                {
                    "role": "system",
                    "content": (
                        system_prompt
                        + "\n\n你正在修正前一次輸出。請輸出壓縮、完整、可被 json.loads 解析的 JSON object。"
                        "不要輸出說明文字。markdown_content 請摘要化並限制在 2500 字以內。"
                    ),
                },
                {"role": "user", "content": base_user_prompt},
            ],
            EXTRACTION_RETRY_MAX_COMPLETION_TOKENS,
        ),
    ]

    for attempt_number, (messages, max_tokens) in enumerate(attempts, start=1):
        try:
            raw_content, finish_reason = _call_extraction_model(messages, max_tokens)
        except Exception as e:
            logger.error(f"[Scheduler] AI Extraction request failed for {url}: {e}", exc_info=True)
            return {}

        if finish_reason == "length":
            logger.warning(
                f"[Scheduler] AI extraction output may be truncated for {url} "
                f"(attempt={attempt_number}, max_completion_tokens={max_tokens})."
            )

        parsed = _parse_extraction_json(raw_content, url, finish_reason, attempt_number)
        if parsed:
            return parsed

    logger.error(f"[Scheduler] AI Extraction failed for {url}: model did not return valid JSON after retry.")
    return {}

def process_scholarship_update(row, new_hash, new_text):
    """
    [REVIEW MODE] 偵測到內容變更後，不自動更新 DB 與 Milvus。
    改為將 AI 萃取結果暫存至 pending_data，並設 needs_review=True，
    等待管理員手動審核後才正式儲存。
    """
    scholarship_code, title, url = row[0], row[1], row[2]
    logger.info(f"[Scheduler] Content changed for '{title}', running AI extraction for pending review...")
    
    extracted_data = ask_ai_to_extract(url, new_text)
    if not extracted_data:
        logger.warning(f"[Scheduler] AI extraction returned empty for {title}, skipping.")
        return False

    extracted_data['link'] = url
    extracted_data['scholarship_code'] = scholarship_code

    # 防呆：確保字串欄位不為 dict/list
    for field in ['title', 'category', 'amount_summary', 'description', 'application_date_text', 'contact', 'markdown_content']:
        val = extracted_data.get(field, "")
        if isinstance(val, (dict, list)):
            extracted_data[field] = json.dumps(val, ensure_ascii=False)
        else:
            extracted_data[field] = str(val) if val is not None else ""

    # 只寫入 pending_data 和 needs_review，不動主欄位和 Milvus
    try:
        now = datetime.now(timezone.utc)
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(
                """
                UPDATE tcuscholarships
                SET pending_data = %s, needs_review = TRUE, last_checked_at = %s
                WHERE scholarship_code = %s
                """,
                (json.dumps(extracted_data, ensure_ascii=False), now.isoformat(), scholarship_code)
            )
        logger.info(f"[Scheduler] pending_data saved for '{title}', awaiting admin review.")
        return True
    except Exception as e:
        logger.error(f"[Scheduler] Failed to save pending_data for {title}: {e}", exc_info=True)
        try:
            send_line_message(f"❌ [系統通知] 暫存草稿失敗\n名稱: {title}\n錯誤: {e}")
        except Exception:
            pass
        return False


def run_inspection():
    logger.info(f"\n[Scheduler] Running scholarship inspection at {datetime.now().isoformat()}")
    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT scholarship_code, title, link, content_hash FROM tcuscholarships WHERE link IS NOT NULL AND link != '';")
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"[Scheduler] Inspection failed to fetch rows: {e}", exc_info=True)
        return

    if not rows:
        return

    # [PERF-3] 並行爬取所有網址，全面升級為徹底非阻塞的 aiohttp
    # 相比於 ThreadPool，效能跳躍性提升、佔用資源極少。
    logger.info(f"[Scheduler] Scraping {len(rows)} URLs concurrently using aiohttp...")
    
    # 使用 asyncio.run 啟動異步驅動
    scraped_results = asyncio.run(_async_run_inspection(rows))

    # 爬取完成後，依序處理有變化的項目
    changed_items = []
    for row, latest_text in scraped_results:
        scholarship_code, title, url, old_hash = row
        if not latest_text:
            continue
            
        new_hash = compute_md5(latest_text)
        
        if old_hash != new_hash:
            logger.info(f"[Scheduler] Content change detected for {title} ({url})")
            success = process_scholarship_update(row, new_hash, latest_text)
            if success:
                changed_items.append((title, url))
        else:
            try:
                with get_db_cursor(commit=True) as (update_conn, c2):
                    now = datetime.now(timezone.utc)
                    c2.execute("UPDATE tcuscholarships SET last_checked_at = %s WHERE scholarship_code = %s", (now.isoformat(), scholarship_code))
            except Exception as e:
                logger.warning(f"Failed to update last_checked for {title}: {e}")
    
    logger.info(f"[Scheduler] Inspection complete. {len(changed_items)}/{len(scraped_results)} changed successfully.")
    
    # [NEW] 不論有無變動，自檢完成後都發送一個總結通知
    try:
        if changed_items:
            # 限制列出的變更項目數量，避免 Line 訊息過長
            max_display = 15
            display_items = changed_items[:max_display]
            details = "\n".join([f"🔹 {t}" for t, u in display_items])
            if len(changed_items) > max_display:
                details += f"\n...及其他 {len(changed_items) - max_display} 項"
                
            summary_msg = (
                f"📊 [系統自動檢測完成]\n"
                f"檢查時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"本次檢查項目：{len(rows)} 筆\n"
                f"偵測到變動並待審核：{len(changed_items)} 筆\n\n"
                f"【變更清單】\n{details}\n\n"
                f"💡 AI 已完成萃取，請至管理後台審核並手動儲存。"
            )
        else:
            summary_msg = (
                f"📊 [系統自動檢測完成]\n"
                f"檢查時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"本次檢查項目：{len(rows)} 筆\n"
                f"偵測到變動：0 筆\n"
                f"狀態：自檢程序已順利執行完畢，無任何變更。"
            )
        send_line_message(summary_msg)
    except Exception as e:
        logger.warning(f"Failed to send summary notification: {e}")


def cleanup_langgraph_checkpoints(retention_days: int | None = None):
    """Keep LangGraph PostgreSQL checkpoints for recent sessions only."""
    retention_days = retention_days or config.CHECKPOINT_RETENTION_DAYS
    if retention_days <= 0:
        logger.info("[Checkpoint Cleanup] Disabled because retention_days <= 0.")
        return

    logger.info(f"[Checkpoint Cleanup] Removing LangGraph checkpoints older than {retention_days} days.")

    try:
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(
                """
                SELECT to_regclass('checkpoints'),
                       to_regclass('checkpoint_writes'),
                       to_regclass('checkpoint_blobs');
                """
            )
            checkpoints_table, writes_table, blobs_table = cursor.fetchone()
            if not checkpoints_table:
                logger.info("[Checkpoint Cleanup] LangGraph checkpoint tables do not exist yet; skipping.")
                return

            cursor.execute("ALTER TABLE IF EXISTS checkpoints ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            cursor.execute("ALTER TABLE IF EXISTS checkpoint_writes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            cursor.execute("ALTER TABLE IF EXISTS checkpoint_blobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")

            cutoff_interval = f"{int(retention_days)} days"

            deleted_writes = 0
            if writes_table:
                cursor.execute(
                    """
                    DELETE FROM checkpoint_writes cw
                    USING checkpoints cp
                    WHERE cw.thread_id = cp.thread_id
                      AND cw.checkpoint_ns = cp.checkpoint_ns
                      AND cw.checkpoint_id = cp.checkpoint_id
                      AND COALESCE((cp.checkpoint ->> 'ts')::timestamptz, cp.created_at) < NOW() - %s::interval;
                    """,
                    (cutoff_interval,),
                )
                deleted_writes = cursor.rowcount

            cursor.execute(
                """
                DELETE FROM checkpoints
                WHERE COALESCE((checkpoint ->> 'ts')::timestamptz, created_at) < NOW() - %s::interval;
                """,
                (cutoff_interval,),
            )
            deleted_checkpoints = cursor.rowcount

            deleted_blobs = 0
            if blobs_table:
                cursor.execute(
                    """
                    DELETE FROM checkpoint_blobs bl
                    WHERE NOT EXISTS (
                          SELECT 1
                          FROM checkpoints cp
                          WHERE cp.thread_id = bl.thread_id
                            AND cp.checkpoint_ns = bl.checkpoint_ns
                            AND cp.checkpoint -> 'channel_versions' ->> bl.channel = bl.version
                      );
                    """,
                )
                deleted_blobs = cursor.rowcount

            logger.info(
                "[Checkpoint Cleanup] Deleted checkpoints=%s, writes=%s, blobs=%s.",
                deleted_checkpoints,
                deleted_writes,
                deleted_blobs,
            )
    except Exception as e:
        logger.warning(f"[Checkpoint Cleanup] Failed: {e}", exc_info=True)


def cleanup_qa_logs(retention_days: int | None = None):
    """Delete old chat QA logs to reduce retained user data."""
    retention_days = retention_days if retention_days is not None else config.QA_LOG_RETENTION_DAYS
    if retention_days <= 0:
        logger.info("[QA Log Cleanup] Disabled because retention_days <= 0.")
        return

    logger.info(f"[QA Log Cleanup] Removing QA logs older than {retention_days} days.")

    try:
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(
                pg_sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (timestamp);").format(
                    pg_sql.Identifier(f"idx_{config.DB_TABLE_NAME}_timestamp"),
                    pg_sql.Identifier(config.DB_TABLE_NAME),
                )
            )
            cursor.execute(
                pg_sql.SQL(
                    """
                    DELETE FROM {}
                    WHERE timestamp < NOW() - %s::interval;
                    """
                ).format(pg_sql.Identifier(config.DB_TABLE_NAME)),
                (f"{int(retention_days)} days",),
            )
            logger.info(f"[QA Log Cleanup] Deleted qa_logs={cursor.rowcount}.")
    except Exception as e:
        logger.warning(f"[QA Log Cleanup] Failed: {e}", exc_info=True)


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run every 24 hours
    scheduler.add_job(run_inspection_once, IntervalTrigger(hours=24), id='scholarship_inspection')
    scheduler.add_job(
        cleanup_langgraph_checkpoints_once,
        IntervalTrigger(hours=CHECKPOINT_CLEANUP_INTERVAL_HOURS),
        id='langgraph_checkpoint_cleanup',
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        cleanup_qa_logs_once,
        IntervalTrigger(hours=CHECKPOINT_CLEANUP_INTERVAL_HOURS),
        id='qa_log_cleanup',
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    logger.info("[Scheduler] Started background automated inspection and checkpoint cleanup.")

if __name__ == "__main__":
    # 允許您直接執行 `python scheduler.py` 進行手動測試
    logger.info("[Scheduler] Manual execution triggered.")
    run_inspection()
