import time
import uuid
import hashlib
import requests
import json
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed  # [PERF-3] 並行爬取

import config
from admin_api import get_db_connection, release_db_connection, openai_client, init_milvus_collection, emb_texts_batch  # [CODE-2]
from langchain_text_splitters import RecursiveCharacterTextSplitter
from logger import get_logger
logger = get_logger(__name__)

def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def scrape_url_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.warning(f"[Scheduler] Failed to scrape {url}: {e}")
        return ""

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
    scholarship_code, title, url = row[0], row[1], row[2]
    print(f"[Scheduler] AI re-extracting {title} from {url}")
    
    extracted_data = ask_ai_to_extract(url, new_text)
    if not extracted_data:
        return

    extracted_data['link'] = url

    # 1. Update DB
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        update_query = """
        UPDATE scholarships SET
            title = %s, category = %s, education_system = %s, tags = %s, identity = %s,
            amount_summary = %s, description = %s, application_date_text = %s, contact = %s, 
            markdown_content = %s, content_hash = %s, last_checked_at = %s
        WHERE scholarship_code = %s;
        """
        now = datetime.now(timezone.utc)
        cursor.execute(update_query, (
            extracted_data.get('title', title),
            extracted_data.get('category', ''),
            json.dumps(extracted_data.get('education_system', []), ensure_ascii=False),
            json.dumps(extracted_data.get('tags', []), ensure_ascii=False),
            json.dumps(extracted_data.get('identity', []), ensure_ascii=False),
            extracted_data.get('amount_summary', ''),
            extracted_data.get('description', ''),
            extracted_data.get('application_date_text', ''),
            extracted_data.get('contact', ''),
            extracted_data.get('markdown_content', ''),
            new_hash,
            now.isoformat(),
            scholarship_code
        ))
        conn.commit()
    except Exception as e:
        print(f"[Scheduler] DB Update failed: {e}")
        return
    finally:
        release_db_connection(conn)  # [SEC-3] 歸還連線池

    # 2. Update Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        
        # Delete old chunks
        milvus_client.delete(collection_name=collection_name, filter=f"source_path == '{scholarship_code}'")
        milvus_client.flush(collection_name=collection_name)
        
        # Insert new chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = [c.strip() for c in text_splitter.split_text(extracted_data.get('markdown_content', '')) if c.strip()]
        
        if chunks:
            # [PERF-1] 批次嵌入
            vectors = emb_texts_batch(chunks)
            source_name = extracted_data.get('title') or title or "unknown_scholarship"
            data_to_insert = []
            for chunk, vector in zip(chunks, vectors):
                data_to_insert.append({
                    "id": uuid.uuid4().int >> 64,  # [CODE-2] UUID 確保唯一性
                    "text": chunk,
                    "source_file": source_name + ".md",
                    "source_path": scholarship_code,
                    "source_url": url,
                    "identity": extracted_data.get('identity', []),
                    "education_system": extracted_data.get('education_system', []),
                    "category": [extracted_data.get('category', '')] if extracted_data.get('category', '') else [],
                    "tags": extracted_data.get('tags', []),
                    "vector": vector
                })

            milvus_client.insert(collection_name=collection_name, data=data_to_insert)
            milvus_client.flush(collection_name=collection_name)
            
        logger.info(f"[Scheduler] Successfully updated Milvus chunks for {title}")
    except Exception as e:
        logger.error(f"[Scheduler] Milvus Update failed: {e}", exc_info=True)


def run_inspection():
    logger.info(f"\n[Scheduler] Running scholarship inspection at {datetime.now().isoformat()}")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT scholarship_code, title, link, content_hash FROM scholarships WHERE link IS NOT NULL AND link != '';")
        rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"[Scheduler] Inspection failed to fetch rows: {e}", exc_info=True)
        release_db_connection(conn)
        return
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()

    if not rows:
        release_db_connection(conn)
        return

    # [PERF-3] 並行爬取所有網址，透過線程池同時發請求
    # 50 筆 × 串行3s = 150s  vs  50 筆 × 並行(5線程) = ~30s
    logger.info(f"[Scheduler] Scraping {len(rows)} URLs concurrently (max 5 workers)...")
    
    def scrape_row(row):
        scholarship_code, title, url, old_hash = row
        latest_text = scrape_url_text(url)
        return row, latest_text

    scraped_results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_row, row): row for row in rows}
        for future in as_completed(futures):
            try:
                row, latest_text = future.result()
                scraped_results.append((row, latest_text))
            except Exception as e:
                logger.warning(f"[Scheduler] Scrape error for {futures[future][2]}: {e}")

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
                update_conn = get_db_connection()
                c2 = update_conn.cursor()
                now = datetime.now(timezone.utc)
                c2.execute("UPDATE scholarships SET last_checked_at = %s WHERE scholarship_code = %s", (now.isoformat(), scholarship_code))
                update_conn.commit()
                c2.close()
                release_db_connection(update_conn)
            except Exception as e:
                logger.warning(f"Failed to update last_checked for {title}: {e}")
    
    release_db_connection(conn)
    logger.info(f"[Scheduler] Inspection complete. {changed_count}/{len(scraped_results)} changed.")


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run every 12 hours
    scheduler.add_job(run_inspection, IntervalTrigger(minutes=720), id='scholarship_inspection')
    scheduler.start()
    logger.info("[Scheduler] Started background automated inspection.")
