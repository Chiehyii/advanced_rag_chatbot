import re
import uuid
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel
from openai import OpenAI
import config
import hashlib
from datetime import datetime, timedelta, timezone
import jwt
from utils import is_safe_url
from logger import get_logger
from prompts import PROMPTS
from milvus_service import init_milvus_collection, _insert_chunks_to_milvus
from scraper_service import _get_hash_if_url
from db import get_db_cursor

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

# [SEC-4] 管理後台專屬的速率限制器
limiter = Limiter(key_func=get_remote_address)

# --- Models ---
class ExtractRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None

class ScholarshipForm(BaseModel):
    scholarship_code: str
    title: str
    link: Optional[str] = ""
    category: Optional[str] = ""
    education_system: List[str] = []
    tags: List[str] = []
    identity: List[str] = []
    amount_summary: Optional[str] = ""
    description: Optional[str] = ""
    application_date_text: Optional[str] = ""
    contact: Optional[str] = ""
    markdown_content: str

# --- Security Setup ---
import bcrypt
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def create_access_token(data: dict, expires_delta: timedelta | None = None, token_type: str = "access"):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire, "type": token_type})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt

def verify_admin(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if username is None or username != config.ADMIN_USERNAME or token_type != "access":
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    return username

# --- Dashboard Endpoints ---

@router.get("/dashboard/summary")
def dashboard_summary(current_admin: str = Depends(verify_admin)):
    """Dashboard KPI 摘要：今日提問數、獨立使用者、平均延遲、Token 消耗、滿意度、峰值負載"""
    try:
        with get_db_cursor() as (conn, cursor):
            table = config.DB_TABLE_NAME
            # --- 基礎 KPI ---
            cursor.execute(f"""
                SELECT
                    COUNT(*) AS today_queries,
                    COUNT(DISTINCT user_id) AS unique_users,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens
                FROM {table}
                WHERE timestamp::date = CURRENT_DATE;
            """)
            row = cursor.fetchone()
            today_queries = row[0] or 0
            unique_users = row[1] or 0
            avg_latency = round(float(row[2] or 0), 1)
            total_tokens = int(row[3] or 0)
            prompt_tokens = int(row[4] or 0)
            completion_tokens = int(row[5] or 0)

            # --- 滿意度 ---
            cursor.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE feedback_type = 'like') AS likes,
                    COUNT(*) FILTER (WHERE feedback_type IS NOT NULL AND feedback_type != '') AS total_feedback
                FROM {table}
                WHERE timestamp::date = CURRENT_DATE;
            """)
            fb = cursor.fetchone()
            likes = fb[0] or 0
            total_feedback = fb[1] or 0
            satisfaction = round(likes / total_feedback, 2) if total_feedback > 0 else None

            # --- Peak RPM (今日每分鐘最高請求數) ---
            cursor.execute(f"""
                SELECT
                    COUNT(*) AS cnt,
                    date_trunc('minute', timestamp) AS minute_bucket
                FROM {table}
                WHERE timestamp::date = CURRENT_DATE
                GROUP BY minute_bucket
                ORDER BY cnt DESC
                LIMIT 1;
            """)
            peak_row = cursor.fetchone()
            peak_rpm = int(peak_row[0]) if peak_row else 0
            peak_rpm_time = peak_row[1].strftime("%H:%M") if peak_row else None

            return {
                "status": "success",
                "data": {
                    "today_queries": today_queries,
                    "unique_users": unique_users,
                    "avg_latency_ms": avg_latency,
                    "total_tokens": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "satisfaction_rate": satisfaction,
                    "peak_rpm": peak_rpm,
                    "peak_rpm_time": peak_rpm_time,
                }
            }
    except Exception as e:
        logger.error(f"[Dashboard] summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dashboard summary failed")


@router.get("/dashboard/trends")
def dashboard_trends(
    start_date: str | None = None,
    end_date: str | None = None,
    current_admin: str = Depends(verify_admin),
):
    """Dashboard 趨勢圖：指定日期範圍的每日提問數、Token 消耗與獨立使用者數"""
    from datetime import date as date_type
    # 預設：過去 7 天
    today = date_type.today()
    try:
        d_end = date_type.fromisoformat(end_date) if end_date else today
        d_start = date_type.fromisoformat(start_date) if start_date else d_end - timedelta(days=6)
    except ValueError:
        d_end = today
        d_start = today - timedelta(days=6)

    # 安全限制：最多 365 天
    if (d_end - d_start).days > 365:
        d_start = d_end - timedelta(days=365)
    if d_start > d_end:
        d_start, d_end = d_end, d_start

    try:
        with get_db_cursor() as (conn, cursor):
            table = config.DB_TABLE_NAME
            cursor.execute(f"""
                SELECT
                    timestamp::date AS day,
                    COUNT(*) AS queries,
                    COALESCE(SUM(total_tokens), 0) AS tokens,
                    COUNT(DISTINCT user_id) AS unique_users,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency
                FROM {table}
                WHERE timestamp::date >= %s AND timestamp::date <= %s
                GROUP BY day
                ORDER BY day;
            """, (d_start.isoformat(), d_end.isoformat()))
            rows = cursor.fetchall()
            labels = [r[0].strftime("%m/%d") for r in rows]
            queries = [r[1] for r in rows]
            tokens = [int(r[2]) for r in rows]
            unique_users = [r[3] for r in rows]
            avg_latency = [round(float(r[4]), 1) for r in rows]

            return {
                "status": "success",
                "data": {
                    "labels": labels,
                    "queries": queries,
                    "tokens": tokens,
                    "unique_users": unique_users,
                    "avg_latency": avg_latency,
                }
            }
    except Exception as e:
        logger.error(f"[Dashboard] trends error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dashboard trends failed")


@router.get("/dashboard/recent")
def dashboard_recent(limit: int = 20, current_admin: str = Depends(verify_admin)):
    """Dashboard 近期對話抽查：最近 N 筆對話紀錄"""
    if limit < 1 or limit > 100:
        limit = 20
    try:
        with get_db_cursor() as (conn, cursor):
            table = config.DB_TABLE_NAME
            cursor.execute(f"""
                SELECT id, timestamp, question, answer, latency_ms, total_tokens, feedback_type
                FROM {table}
                ORDER BY timestamp DESC
                LIMIT %s;
            """, (limit,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": r[0],
                    "timestamp": r[1].isoformat() if r[1] else None,
                    "question": r[2] or "",
                    "answer": (r[3] or "")[:200],  # 節錄前 200 字
                    "latency_ms": round(float(r[4] or 0), 1),
                    "total_tokens": int(r[5] or 0),
                    "feedback_type": r[6],
                })
            return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"[Dashboard] recent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dashboard recent failed")

# --- Endpoints ---

@router.post("/login")
@limiter.limit("5/minute")  # [SEC-4] 防止暴力破解，每個 IP 每分鐘最多嘗試 5 次
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != config.ADMIN_USERNAME:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # [SEC-1] 強制使用 Hash 比對，移除明文備用機制
    if not config.ADMIN_PASSWORD_HASH:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error regarding admin credentials."
        )

    # Bcrypt has a 72-byte limit. Truncate identical to generate_hash.py
    password_to_check = form_data.password[:72].encode('utf-8')
    try:
        is_valid = bcrypt.checkpw(password_to_check, config.ADMIN_PASSWORD_HASH.encode('utf-8'))
    except ValueError:
        is_valid = False

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": config.ADMIN_USERNAME}, expires_delta=access_token_expires, token_type="access"
    )
    
    refresh_token_expires = timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_access_token(
        data={"sub": config.ADMIN_USERNAME}, expires_delta=refresh_token_expires, token_type="refresh"
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

class RefreshTokenRequest(BaseModel):
    refresh_token: str

@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, refresh_request: RefreshTokenRequest):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_request.refresh_token, config.JWT_SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if username is None or username != config.ADMIN_USERNAME or token_type != "refresh":
            raise credentials_exception
            
        access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": config.ADMIN_USERNAME}, expires_delta=access_token_expires, token_type="access"
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except jwt.InvalidTokenError:
        raise credentials_exception

def _parse_json_array(value):
    """Safely parse a JSON string into a list. Returns [] on failure."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []

def validate_scholarship_code(scholarship_code: str) -> str:
    """
    [SEC-2] 白名單驗證 scholarship_code，防止 Milvus filter 字串注入。
    只允許英數字、連字符和底線，拒絕所有特殊字元。
    """
    if not re.match(r'^[a-zA-Z0-9\-_]+$', scholarship_code):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scholarship_code format: '{scholarship_code}'. Only alphanumeric characters, hyphens, and underscores are allowed."
        )
    return scholarship_code

@router.get("/scholarships")
def list_scholarships(current_admin: str = Depends(verify_admin)):
    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT scholarship_code, title, link, category, created_at, education_system, tags, identity, needs_review FROM scholarships ORDER BY created_at DESC;")
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "scholarship_code": str(row[0]),
                    "title": row[1],
                    "link": row[2],
                    "category": row[3],
                    "created_at": str(row[4]),
                    "education_system": _parse_json_array(row[5]),
                    "tags": _parse_json_array(row[6]),
                    "identity": _parse_json_array(row[7]),
                    "needs_review": bool(row[8]) if row[8] is not None else False,
                })
            return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"[Admin API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/scholarships/{scholarship_code}")
def get_scholarship(scholarship_code: str, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]
    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT scholarship_code, title, link, category, education_system, tags, identity, amount_summary, description, application_date_text, contact, markdown_content, needs_review, pending_data FROM scholarships WHERE scholarship_code = %s;", (scholarship_code,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Scholarship not found")
                
            data = {
                "scholarship_code": str(row[0]),
                "title": row[1],
                "link": row[2],
                "category": row[3],
                "education_system": _parse_json_array(row[4]),
                "tags": _parse_json_array(row[5]),
                "identity": _parse_json_array(row[6]),
                "amount_summary": row[7],
                "description": row[8],
                "application_date_text": row[9],
                "contact": row[10],
                "markdown_content": row[11],
                "needs_review": bool(row[12]) if row[12] is not None else False,
                "pending_data": row[13] if row[13] is not None else None,
            }
            return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Admin API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.patch("/scholarships/{scholarship_code}/discard_pending")
def discard_pending(scholarship_code: str, current_admin: str = Depends(verify_admin)):
    """管理員捨棄 Scheduler 暫存的草稿，清除 pending_data 並取消待處理標記。"""
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]
    try:
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(
                "UPDATE scholarships SET needs_review = FALSE, pending_data = NULL WHERE scholarship_code = %s",
                (scholarship_code,)
            )
        return {"status": "success", "message": "Pending changes discarded"}
    except Exception as e:
        logger.error(f"[Admin API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/extract_info")
def extract_scholarship_info(request: ExtractRequest, current_admin: str = Depends(verify_admin)):
    if not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Must provide either 'url' or 'text'")
    
    content_to_process = ""
    
    if request.url:
        if not is_safe_url(request.url):
            raise HTTPException(status_code=400, detail="The provided URL is not safe to scrape (disallowed IP/domain).")
        try:
            resp = requests.get(request.url, timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")
            # Extract basic text
            content_to_process = soup.get_text(separator="\n", strip=True)
            content_to_process = f"URL: {request.url}\n\nContent:\n{content_to_process}"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to load URL: {e}")
    else:
        content_to_process = request.text
        
    system_prompt = PROMPTS['zh']['extraction_system']
    
    try:
        response = openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "請擷取以下內容：\n\n" + content_to_process[:8000]} # Limit to avoid context window explosion
            ],
            response_format={ "type": "json_object" }
        )
        
        extracted_data = json.loads(response.choices[0].message.content)
        extracted_data["scholarship_code"] = "sch-" + str(uuid.uuid4())[:8]
        if request.url and not extracted_data.get("link"):
            extracted_data["link"] = request.url

        return {"status": "success", "data": extracted_data}
        
    except Exception as e:
        logger.error(f"[Admin API] extract_scholarship_info error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Extraction failed due to internal error.")


@router.post("/scholarships")
def save_scholarship(form: ScholarshipForm, current_admin: str = Depends(verify_admin)):
    # 1. Save to PostgreSQL
    try:
        new_hash, current_time = _get_hash_if_url(form.link)
        
        insert_query = """
        INSERT INTO scholarships (
            scholarship_code, title, link, category, education_system, tags, identity,
            amount_summary, description, application_date_text, contact, markdown_content,
            content_hash, last_checked_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (scholarship_code) DO UPDATE SET
            title = EXCLUDED.title,
            link = EXCLUDED.link,
            category = EXCLUDED.category,
            education_system = EXCLUDED.education_system,
            tags = EXCLUDED.tags,
            identity = EXCLUDED.identity,
            amount_summary = EXCLUDED.amount_summary,
            description = EXCLUDED.description,
            application_date_text = EXCLUDED.application_date_text,
            contact = EXCLUDED.contact,
            markdown_content = EXCLUDED.markdown_content,
            content_hash = EXCLUDED.content_hash,
            last_checked_at = EXCLUDED.last_checked_at;
        """
        
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(insert_query, (
                form.scholarship_code, form.title, form.link, form.category,
                json.dumps(form.education_system, ensure_ascii=False),
                json.dumps(form.tags, ensure_ascii=False),
                json.dumps(form.identity, ensure_ascii=False),
                form.amount_summary, form.description, form.application_date_text,
                form.contact, form.markdown_content, new_hash, current_time
            ))
    except Exception as e:
        logger.error(f"[Admin API] DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="DB Error")

    # 2. Insert vector chunks into Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        # [CODE-1] 共用 helper：切分 + 批次嵌入 + 寫入 Milvus
        count = _insert_chunks_to_milvus(
            milvus_client, collection_name,
            form.markdown_content, form.title,
            form.scholarship_code, form.link or "",
            form.identity, form.education_system,
            form.category, form.tags
        )
        return {"status": "success", "message": f"Saved {count} chunks to Knowledge Base"}
    except Exception as e:
        logger.error(f"[Admin API] Vector DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Vector DB Error")

@router.put("/scholarships/{scholarship_code}")
def update_scholarship(scholarship_code: str, form: ScholarshipForm, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]

    # 1. Update PostgreSQL (also clear pending review state)
    try:
        new_hash, current_time = _get_hash_if_url(form.link)
        update_query = """
        UPDATE scholarships SET
            title = %s, link = %s, category = %s, education_system = %s, tags = %s, identity = %s,
            amount_summary = %s, description = %s, application_date_text = %s, contact = %s,
            markdown_content = %s, content_hash = %s, last_checked_at = %s,
            needs_review = FALSE, pending_data = NULL
        WHERE scholarship_code = %s;
        """
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute(update_query, (
                form.title, form.link, form.category,
                json.dumps(form.education_system, ensure_ascii=False),
                json.dumps(form.tags, ensure_ascii=False),
                json.dumps(form.identity, ensure_ascii=False),
                form.amount_summary, form.description,
                form.application_date_text, form.contact, form.markdown_content,
                new_hash, current_time, scholarship_code
            ))
    except Exception as e:
        logger.error(f"[Admin API] DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="DB Error")

    # 2. Re-Insert vector chunks into Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        # Delete old chunks first, then re-insert
        milvus_client.delete(collection_name=collection_name, filter=f"source_path == '{scholarship_code}'")
        milvus_client.flush(collection_name=collection_name)
        # [CODE-1] 共用 helper：切分 + 批次嵌入 + 寫入 Milvus
        count = _insert_chunks_to_milvus(
            milvus_client, collection_name,
            form.markdown_content, form.title,
            scholarship_code, form.link or "",
            form.identity, form.education_system,
            form.category, form.tags
        )
        return {"status": "success", "message": f"Updated {count} chunks in Knowledge Base"}
    except Exception as e:
        logger.error(f"[Admin API] Vector DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Vector DB Error")



@router.delete("/scholarships/{scholarship_code}")
def delete_scholarship(scholarship_code: str, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]

    # [OPT-4] 先刪 Milvus 向量，確認成功後再刪 PostgreSQL
    # 原因：若先刪 DB 再刪 Milvus，Milvus 失敗 → 殭屍向量（查得到文件但找不到來源）
    # 現在：Milvus 失敗 → DB 記錄保留 → 可安全重試，無資料不一致問題

    # 1. 先刪除 Milvus 向量（失敗時 DB 記錄仍安全保留）
    try:
        milvus_client, collection_name = init_milvus_collection()
        milvus_client.delete(
            collection_name=collection_name,
            filter=f"source_path == '{scholarship_code}'"
        )
        milvus_client.flush(collection_name=collection_name)
    except Exception as e:
        logger.error(f"[Admin API] delete_scholarship Vector DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Vector DB Error (DB record preserved)")

    # 2. Milvus 刪除成功後，再刪 PostgreSQL
    try:
        with get_db_cursor(commit=True) as (conn, cursor):
            cursor.execute("DELETE FROM scholarships WHERE scholarship_code = %s", (scholarship_code,))
        return {"status": "success", "message": "Successfully deleted from Knowledge Base and DB"}
    except Exception as e:
        logger.error(f"[Admin API] delete_scholarship DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="DB Error (vectors already removed)")


 
