import time
import uuid
import hashlib
import requests
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed  # 雖然不再用於 scraping，保留備用
import config
from admin_api import openai_client, init_milvus_collection, emb_texts_batch  # [CODE-2]
from db import get_db_cursor
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils import is_safe_url
from logger import get_logger
from notifier import send_line_message
logger = get_logger(__name__)

def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

async def _fetch_url_text(session: aiohttp.ClientSession, url: str) -> str:
    if not is_safe_url(url):
        logger.warning(f"[Scheduler] Unsafe URL blocked: {url}")
        return ""
    try:
        async with session.get(url, timeout=15) as resp:
            content = await resp.read()
            soup = BeautifulSoup(content, "html.parser")
            return soup.get_text(separator="\n", strip=True)
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
    
    async def fetch_row(session, row):
        scholarship_code, title, url, old_hash = row
        async with sem:
            latest_text = await _fetch_url_text(session, url)
        return row, latest_text
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_row(session, row) for row in rows]
        # 並發執行，某個失敗不會中斷全域
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"[Scheduler] Scrape error during gather: {res}")
        else:
            scraped_results.append(res)
            
    return scraped_results

def ask_ai_to_extract(url: str, content: str) -> dict:
    system_prompt = """
    你是一個獎學金資訊擷取的專家助理。請從收到的內容中提取所需的資訊並以 JSON 格式回傳。
    請提取以下欄位：
    - title (名稱)
    - link (網址 - 若內容有提供的話)
    - category (衣珠類別，例如: "生活無憂", 如果沒有請寫 "")
    - education_system (學制：陣列)
    - tags (類別/種類：陣列)
    - identity (身分：陣列)
    - amount_summary (金額說明)
    - description (介紹 - 簡要描述)
    - application_date_text (申請日期)
    - contact (聯絡人)
    - markdown_content (請把所有資訊整理成一篇詳細的 Markdown 文章，用於存入知識庫。文章應該包含所有重要細節與資格條件)
    
    回傳的 JSON 需要包含上述 key 值。不要回傳 markdown 代碼塊格式，只需回傳合法的 JSON 字串。
    """
    try:
        safe_content = content[:8000] if content else ""
        response = openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"URL: {url}\n\nContent:\n" + safe_content}
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[Scheduler] AI Extraction failed for {url}: {e}")
        return {}

def process_scholarship_update(row, new_hash, new_text):
    """
    [REVIEW MODE] 偵測到內容變更後，不再自動更新 DB 與 Milvus。
    改為將 AI 萃取結果暫存至 pending_data，並設 needs_review=True，
    等待管理員手動審核後才正式儲存。
    """
    scholarship_code, title, url = row[0], row[1], row[2]
    logger.info(f"[Scheduler] Content changed for '{title}', running AI extraction for pending review...")
    
    extracted_data = ask_ai_to_extract(url, new_text)
    if not extracted_data:
        logger.warning(f"[Scheduler] AI extraction returned empty for {title}, skipping.")
        return

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
                UPDATE scholarships
                SET pending_data = %s, needs_review = TRUE, last_checked_at = %s
                WHERE scholarship_code = %s
                """,
                (json.dumps(extracted_data, ensure_ascii=False), now.isoformat(), scholarship_code)
            )
        logger.info(f"[Scheduler] pending_data saved for '{title}', awaiting admin review.")
        try:
            send_line_message(
                f"🔔 [系統通知] 偵測到獎學金內容變更\n"
                f"名稱: {title}\n網址: {url}\n"
                f"AI 已完成萃取，請至後台審核並手動儲存。"
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[Scheduler] Failed to save pending_data for {title}: {e}", exc_info=True)
        try:
            send_line_message(f"❌ [系統通知] 暫存草稿失敗\n名稱: {title}\n錯誤: {e}")
        except Exception:
            pass


def run_inspection():
    logger.info(f"\n[Scheduler] Running scholarship inspection at {datetime.now().isoformat()}")
    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT scholarship_code, title, link, content_hash FROM scholarships WHERE link IS NOT NULL AND link != '';")
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
    changed_count = 0
    for row, latest_text in scraped_results:
        scholarship_code, title, url, old_hash = row
        if not latest_text:
            continue
            
        new_hash = compute_md5(latest_text)
        
        if old_hash != new_hash:
            print(f"[Scheduler] Content change detected for {title} ({url})")
            changed_count += 1
            process_scholarship_update(row, new_hash, latest_text)
        else:
            try:
                with get_db_cursor(commit=True) as (update_conn, c2):
                    now = datetime.now(timezone.utc)
                    c2.execute("UPDATE scholarships SET last_checked_at = %s WHERE scholarship_code = %s", (now.isoformat(), scholarship_code))
            except Exception as e:
                logger.warning(f"Failed to update last_checked for {title}: {e}")
    
    logger.info(f"[Scheduler] Inspection complete. {changed_count}/{len(scraped_results)} changed.")
    
    # [NEW] 不論有無變動，自檢完成後都發送一個總結通知
    try:
        summary_msg = (
            f"📊 [系統自動檢測完成]\n"
            f"檢查時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"本次檢查項目：{len(rows)} 筆\n"
            f"偵測到變動：{changed_count} 筆\n"
            f"狀態：自檢程序已順利執行完畢。"
        )
        send_line_message(summary_msg)
    except Exception as e:
        logger.warning(f"Failed to send summary notification: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run every 12 hours
    scheduler.add_job(run_inspection, IntervalTrigger(minutes=720), id='scholarship_inspection')
    scheduler.start()
    logger.info("[Scheduler] Started background automated inspection.")

if __name__ == "__main__":
    # 允許您直接執行 `python scheduler.py` 進行手動測試
    logger.info("[Scheduler] Manual execution triggered.")
    run_inspection()
