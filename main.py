import os
import sys
import uuid
import config
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import List, Optional
import psycopg2
from psycopg2 import sql as pg_sql
import json
import time
import hashlib
from fastapi.responses import StreamingResponse, JSONResponse
from rag_service import stream_agent_pipeline
import admin_api
from scheduler import start_scheduler
from logger import get_logger, request_id_var
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from security import (
    ANONYMOUS_USER_COOKIE_NAME,
    RequestBodyLimitMiddleware,
    sign_session_id,
    verify_signed_session,
)


def _get_real_ip(request: Request) -> str:
    """
    Read the real client IP safely when behind a reverse proxy.
    Render/Nginx append the real IP as the LAST entry in X-Forwarded-For,
    so we take the last entry instead of the first (which is client-controlled).
    Falls back to the direct TCP connection host if the header is absent.
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if config.TRUST_PROXY_HEADERS and forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(key_func=_get_real_ip)

# 簡單記憶體快取，用於 filter_scholarships (10分鐘 TTL)
_scholarship_cache = {"data": None, "timestamp": 0}

# 取得 logger 實例 (建立這個檔案專屬的 logger)
logger = get_logger(__name__)

# Add the project root to the Python path to allow imports from other files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- API Definition ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    from agent.graph import init_postgres_checkpointer, close_postgres_checkpointer
    await init_postgres_checkpointer()
    start_scheduler()
    yield
    await close_postgres_checkpointer()

_is_production = config.ENVIRONMENT == "production"
app = FastAPI(
    title="Chatbot RAG API",
    description="An API for the Milvus RAG chatbot.",
    version="1.0.0",
    docs_url=None if _is_production else '/docs',
    redoc_url=None if _is_production else '/redoc',
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"[Validation] {request.method} {request.url.path} failed: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS_LIST,  # Use the allowlist from config
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Request-ID", "X-Requested-With"],
    expose_headers=["X-Chat-Session-Token"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=config.MAX_REQUEST_BODY_BYTES)

_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://www.google.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self';"
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = _CSP
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """為每個 HTTP 請求自動產生 Request ID，寫入 contextvars 與 Response Header"""
    rid = str(uuid.uuid4())[:8]  # 取前 8 碼即可，既短又足夠唯一
    request.state.request_id = rid
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

# --- Pydantic Models for Request and Response ---

class HistoryMessage(BaseModel):
    role: str = Field(..., pattern='^(user|assistant)$')
    content: str = Field(..., min_length=1, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def normalize_history_message(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["content"] = str(normalized.get("content") or "").strip()[:2000]
        return normalized

class ChatRequest(BaseModel):
    """[OPT-3] Request model for a user's chat query — with length limits to prevent token abuse."""
    query: str = Field(..., min_length=1, max_length=1000)
    history: List[HistoryMessage] | None = Field(None)
    lang: Optional[str] = Field('zh', pattern='^(zh|en)$')
    title_filter: List[str] | None = Field(None)
    session_id: Optional[str] = Field(None)
    chat_session_token: Optional[str] = Field(None)
    user_id: Optional[str] = Field(None)
    reset_session: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_chat_request(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["query"] = str(normalized.get("query") or "").strip()[:1000]

        raw_history = normalized.get("history") or []
        cleaned_history = []
        if isinstance(raw_history, list):
            for msg in raw_history:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = str(msg.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    cleaned_history.append({"role": role, "content": content[:2000]})
        normalized["history"] = cleaned_history[-20:] if cleaned_history else None

        raw_titles = normalized.get("title_filter") or None
        if isinstance(raw_titles, list):
            normalized["title_filter"] = [
                str(title).strip()[:120]
                for title in raw_titles[:3]
                if str(title).strip()
            ] or None
        else:
            normalized["title_filter"] = None

        for key in ("session_id", "chat_session_token", "user_id"):
            value = normalized.get(key)
            normalized[key] = str(value).strip()[:160] if value else None
        return normalized

class FeedbackRequest(BaseModel):
    """Request model for submitting feedback."""
    log_id: int = Field(..., ge=1)
    feedback_token: str = Field(..., min_length=32, max_length=128)
    feedback_type: Optional[str] = Field(None, pattern='^(like|dislike)$')
    feedback_text: Optional[str] = Field(None, max_length=500)

# --- API Endpoints ---

app.include_router(admin_api.router)

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    db_status = "ok" if getattr(config, 'DB_POOL', None) else "unavailable"
    return {"status": "ok", "db": db_status}

@app.post("/test", include_in_schema=False)
async def test_endpoint(request: Request):
    if _is_production:
        raise HTTPException(status_code=404, detail="Not found")
    body = await request.body()
    return {"body_len": len(body)}

@app.post("/chat")
@limiter.limit(config.RATE_LIMIT_CHAT)
async def chat_endpoint(request: Request):
    """
    Receives a user query and conversation history, processes it through the RAG pipeline,
    and returns a streaming response of the generated answer.
    """
    raw_body = await request.body()
    if not raw_body.strip():
        logger.warning("[Chat] Empty request body")
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        preview = raw_body[:200].decode("utf-8", errors="replace")
        logger.warning(f"[Chat] Invalid JSON request body: {e}; body_preview={preview!r}")
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    if not isinstance(payload, dict):
        logger.warning(f"[Chat] JSON payload must be an object, got {type(payload).__name__}")
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        chat_request = ChatRequest.model_validate(payload)
    except ValidationError as e:
        logger.warning(f"[Chat] Invalid chat request fields: {e.errors()}")
        raise HTTPException(status_code=422, detail=e.errors())

    # request_id comes from middleware; chat session is a per-tab signed token.
    # anonymous user id is a backend-controlled signed cookie for aggregate stats.
    rid = getattr(request.state, 'request_id', '-')
    sid = None if chat_request.reset_session else verify_signed_session(chat_request.chat_session_token, config.JWT_SECRET_KEY)
    sid = sid or uuid.uuid4().hex
    anonymous_user_cookie = request.cookies.get(ANONYMOUS_USER_COOKIE_NAME)
    uid = verify_signed_session(anonymous_user_cookie, config.JWT_SECRET_KEY) or uuid.uuid4().hex
    
    # 📝 INFO：記錄正常的請求進入
    logger.info(f"[Chat] Received new chat stream request (session={sid}, user={uid})")
    
    async def event_generator():
        # 在 async generator 中重新設定 contextvars，確保串流期間的 log 也帶上 request_id
        request_id_var.set(rid)
        try:
            
            # 📝 INFO：記錄使用者的提問與語言
            logger.info(f"[Chat] Processing query stream (length={len(chat_request.query)}, lang={chat_request.lang})")
            
            # --- 壓力測試防護：如果是 MOCK_TEST，直接回傳模擬資料，不進 OpenAI Pipeline ---
            if getattr(config, 'ENVIRONMENT', 'production') != 'production' and chat_request.query == "MOCK_TEST":
                await asyncio.sleep(0.1) # 模擬一點點延遲
                yield f"data: {json.dumps({'type': 'content', 'data': '這是'})}\n\n"
                await asyncio.sleep(0.1)
                yield f"data: {json.dumps({'type': 'content', 'data': '壓力測試模擬回應。'})}\n\n"
                yield f"event: end_stream\ndata: {json.dumps({'type': 'final_data', 'data': {'contexts': [], 'log_id': -1}})}\n\n"
                return
            # ---------------------------------------------------------------------------------

            # The pipeline now yields events (content chunks or final data)
            history_dicts = [msg.model_dump() for msg in chat_request.history] if chat_request.history else []
            async for event in stream_agent_pipeline(chat_request.query, history_dicts, chat_request.lang, title_filter=chat_request.title_filter, request_id=rid, session_id=sid, user_id=uid):
                event_type = event.get("type")
                data = event.get("data")

                if event_type == "content":
                    # Send a standard message event
                    # The data is just the text chunk
                    sse_data = json.dumps({"type": "content", "data": data})
                    yield f"data: {sse_data}\n\n"

                elif event_type == "thinking_step":
                    # Send thinking/progress step to frontend
                    sse_data = json.dumps({"type": "thinking_step", "data": data})
                    yield f"data: {sse_data}\n\n"
                
                elif event_type == "final_data":
                    # Send a custom named event for the final payload
                    # The data is the dict with contexts and log_id
                    sse_data = json.dumps({"type": "final_data", "data": data})
                    yield f"event: end_stream\ndata: {sse_data}\n\n"
                    
                # Yield a small delay to ensure messages are sent separately
                # await asyncio.sleep(0.01)

        except Exception as e:
            # 🚨 ERROR：發生嚴重錯誤。加上 exc_info=True 會自動幫你印出 traceback，不用再寫 traceback.print_exc() 了！
            logger.error(f"[Stream] An exception occurred in stream: {e}", exc_info=True)
            # Optionally, send an error event to the client
            error_message = json.dumps({"type": "error", "data": "An error occurred on the server."})
            yield f"event: error\ndata: {error_message}\n\n"

    response = StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
    response.headers["X-Chat-Session-Token"] = sign_session_id(sid, config.JWT_SECRET_KEY)
    if not verify_signed_session(anonymous_user_cookie, config.JWT_SECRET_KEY):
        response.set_cookie(
            key=ANONYMOUS_USER_COOKIE_NAME,
            value=sign_session_id(uid, config.JWT_SECRET_KEY),
            httponly=True,
            secure=_is_production,
            samesite="none" if _is_production else "lax",
            max_age=60 * 60 * 24 * 90,
        )
    return response

@app.post("/feedback")
@limiter.limit(config.RATE_LIMIT_FEEDBACK)
async def feedback_endpoint(request: Request, feedback_request: FeedbackRequest):
    """
    Receives user feedback and updates the corresponding log entry in the database.
    """
    # 📝 INFO：記錄收到回饋
    logger.info(f"[Feedback] Received feedback for log_id: {feedback_request.log_id}")
    # Move blocking DB operations into a sync helper and run it in a thread
    def _update_feedback(log_id: int, feedback_token: str, feedback_type: str | None, feedback_text: str | None):
        if not config.DB_POOL:
            return False

        # 取得連線池連線
        conn = config.DB_POOL.getconn()
        cursor = None
        try:
            cursor = conn.cursor()
            
            feedback_token_hash = hashlib.sha256(feedback_token.encode("utf-8")).hexdigest()
            update_query = pg_sql.SQL("""UPDATE {}
                             SET feedback_type = %s, feedback_text = %s
                             WHERE id = %s
                               AND feedback_token_hash = %s;""").format(pg_sql.Identifier(config.DB_TABLE_NAME))

            cursor.execute(update_query, (feedback_type, feedback_text, log_id, feedback_token_hash))
            conn.commit()
            return cursor.rowcount == 1
        except psycopg2.Error as e:
            # 🚨 ERROR：資料庫寫入錯誤
            logger.error(f"[DB] Database error in /feedback helper: {e}", exc_info=True)
            return False
        finally:
            if cursor:
                cursor.close()
            # 歸還連線
            if conn:
                config.DB_POOL.putconn(conn)

    # Run the DB update in a thread to avoid blocking the event loop
    ok = await asyncio.to_thread(
        _update_feedback,
        feedback_request.log_id,
        feedback_request.feedback_token,
        feedback_request.feedback_type,
        feedback_request.feedback_text,
    )
    if not ok:
        # Use HTTPException to return proper status code
        raise HTTPException(status_code=403, detail="Invalid feedback token")

    # 📝 INFO：記錄成功更新回饋
    logger.info(f"[Feedback] Successfully updated feedback for log_id: {feedback_request.log_id}")
    return {"status": "success", "message": "Feedback recorded."}

# --- Public Scholarship Filter API ---
@app.get("/scholarships/filter")
@limiter.limit("20/minute")
async def filter_scholarships(request: Request):
    """
    公開端點：回傳獎學金清單（僅包含 title + metadata），供前端篩選 Modal 使用。
    不需要管理員認證，但有速率限制。已加入 10 分鐘記憶體快取。
    """
    global _scholarship_cache
    if _scholarship_cache["data"] is not None and (time.time() - _scholarship_cache["timestamp"] < 600):
        return {"status": "success", "data": _scholarship_cache["data"], "cached": True}

    def _query_scholarships():
        if not config.DB_POOL:
            return []
        conn = config.DB_POOL.getconn()
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT scholarship_code, title, category, tags "
                "FROM scholarships ORDER BY title;"
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                cat = row[2]
                tags_val = row[3]
                # Parse JSON arrays safely
                def _safe_parse(v):
                    if not v:
                        return []
                    if isinstance(v, list):
                        return v
                    try:
                        parsed = json.loads(v)
                        return parsed if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        return []
                result.append({
                    "scholarship_code": str(row[0]),
                    "title": row[1],
                    "category": cat or "",
                    "tags": _safe_parse(tags_val),
                })
            return result
        except Exception as e:
            logger.error(f"[Filter API] Failed to query scholarships: {e}", exc_info=True)
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                config.DB_POOL.putconn(conn)

    data = await asyncio.to_thread(_query_scholarships)
    
    # 更新快取
    _scholarship_cache["data"] = data
    _scholarship_cache["timestamp"] = time.time()
    
    return {"status": "success", "data": data, "cached": False}

# --- Static Files and Schemas ---
@app.get("/metadata_schema.json")
def get_metadata_schema():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_schema.json")
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Schema not found")
# app.mount("/", StaticFiles(directory="frontend-react/dist", html=True), name="frontend-react")
