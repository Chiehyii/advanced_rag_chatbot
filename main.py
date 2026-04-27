import os
import sys
import uuid
import config
from fastapi import FastAPI, HTTPException, Request
import asyncio
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import psycopg2
import traceback
import json
from fastapi.responses import StreamingResponse, JSONResponse
from rag_service import stream_chat_pipeline
import admin_api
from scheduler import start_scheduler
from logger import get_logger, request_id_var
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 建立速率限制器（以 IP 為識別）
limiter = Limiter(key_func=get_remote_address)

# 取得 logger 實例 (建立這個檔案專屬的 logger)
logger = get_logger(__name__)

# Add the project root to the Python path to allow imports from other files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- API Definition ---

app = FastAPI(
    title="Chatbot RAG API",
    description="An API for the Milvus RAG chatbot.",
    version="1.0.0",
    docs_url=None if getattr(config, 'ENVIRONMENT', 'production') == 'production' else '/docs',
    redoc_url=None if getattr(config, 'ENVIRONMENT', 'production') == 'production' else '/redoc',
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
async def startup_event():
    start_scheduler()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS_LIST,  # Use the allowlist from config
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """為所有請求加入 Security Headers"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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

class ChatRequest(BaseModel):
    """[OPT-3] Request model for a user's chat query — with length limits to prevent token abuse."""
    query: str = Field(..., min_length=1, max_length=1000,
                       description="The user's question. Max 1000 characters.")
    history: List[dict] | None = Field(None, max_length=20,
                                       description="Chat history. Max 20 messages.")
    lang: Optional[str] = Field('zh', pattern='^(zh|en)$',
                                description="Language code: 'zh' or 'en' only.")
    title_filter: List[str] | None = Field(None, max_length=3,
                                           description="Optional list of scholarship titles to narrow RAG search. Max 3.")
    session_id: Optional[str] = Field(None, max_length=36,
                                      description="Browser session ID for conversation tracking.")
    user_id: Optional[str] = Field(None, max_length=36,
                                   description="Anonymous browser user ID for user tracking.")

class FeedbackRequest(BaseModel):
    """Request model for submitting feedback."""
    log_id: int
    feedback_type: Optional[str] = None  # "like", "dislike", or null
    feedback_text: Optional[str] = None

# --- API Endpoints ---

app.include_router(admin_api.router)

@app.post("/chat")
@limiter.limit(config.RATE_LIMIT_CHAT)
async def chat_endpoint(request: Request, chat_request: ChatRequest):
    """
    Receives a user query and conversation history, processes it through the RAG pipeline,
    and returns a streaming response of the generated answer.
    """
    # 取出 Middleware 注入的 request_id，以及前端傳入的 session_id / user_id
    rid = getattr(request.state, 'request_id', '-')
    sid = chat_request.session_id
    uid = chat_request.user_id
    
    # 📝 INFO：記錄正常的請求進入
    logger.info(f"[Chat] Received new chat stream request (session={sid}, user={uid})")
    
    async def event_generator():
        # 在 async generator 中重新設定 contextvars，確保串流期間的 log 也帶上 request_id
        request_id_var.set(rid)
        try:
            
            # 📝 INFO：記錄使用者的提問與語言
            logger.info(f"[Chat] Processing query for stream: '{chat_request.query}' in language '{chat_request.lang}'")
            
            # --- 壓力測試防護：如果是 MOCK_TEST，直接回傳模擬資料，不進 OpenAI Pipeline ---
            if chat_request.query == "MOCK_TEST":
                await asyncio.sleep(0.1) # 模擬一點點延遲
                yield f"data: {json.dumps({'type': 'content', 'data': '這是'})}\n\n"
                await asyncio.sleep(0.1)
                yield f"data: {json.dumps({'type': 'content', 'data': '壓力測試模擬回應。'})}\n\n"
                yield f"event: end_stream\ndata: {json.dumps({'type': 'final_data', 'data': {'contexts': [], 'log_id': -1}})}\n\n"
                return
            # ---------------------------------------------------------------------------------

            # The pipeline now yields events (content chunks or final data)
            async for event in stream_chat_pipeline(chat_request.query, chat_request.history or [], chat_request.lang, title_filter=chat_request.title_filter, request_id=rid, session_id=sid, user_id=uid):
                event_type = event.get("type")
                data = event.get("data")

                if event_type == "content":
                    # Send a standard message event
                    # The data is just the text chunk
                    sse_data = json.dumps({"type": "content", "data": data})
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

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/feedback")
@limiter.limit(config.RATE_LIMIT_FEEDBACK)
async def feedback_endpoint(request: Request, feedback_request: FeedbackRequest):
    """
    Receives user feedback and updates the corresponding log entry in the database.
    """
    # 📝 INFO：記錄收到回饋
    logger.info(f"[Feedback] Received feedback for log_id: {feedback_request.log_id}")
    # Move blocking DB operations into a sync helper and run it in a thread
    def _update_feedback(log_id: int, feedback_type: str | None, feedback_text: str | None):
        if not config.DB_POOL:
            return False

        # 取得連線池連線
        conn = config.DB_POOL.getconn()
        cursor = None
        try:
            cursor = conn.cursor()
            
            TABLE_NAME = config.DB_TABLE_NAME
            update_query = f"""UPDATE {TABLE_NAME}
                             SET feedback_type = %s, feedback_text = %s
                             WHERE id = %s;"""

            cursor.execute(update_query, (feedback_type, feedback_text, log_id))
            conn.commit()
            return True
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
    ok = await asyncio.to_thread(_update_feedback, feedback_request.log_id, feedback_request.feedback_type, feedback_request.feedback_text)
    if not ok:
        # Use HTTPException to return proper status code
        raise HTTPException(status_code=500, detail="Failed to record feedback")

    # 📝 INFO：記錄成功更新回饋
    logger.info(f"[Feedback] Successfully updated feedback for log_id: {feedback_request.log_id}")
    return {"status": "success", "message": "Feedback recorded."}

# --- Public Scholarship Filter API ---
@app.get("/scholarships/filter")
@limiter.limit("20/minute")
async def filter_scholarships(request: Request):
    """
    公開端點：回傳獎學金清單（僅包含 title + metadata），供前端篩選 Modal 使用。
    不需要管理員認證，但有速率限制。
    """
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
    return {"status": "success", "data": data}

# --- Static Files and Schemas ---
@app.get("/metadata_schema.json")
def get_metadata_schema():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_schema.json")
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Schema not found")
# app.mount("/", StaticFiles(directory="frontend-react/dist", html=True), name="frontend-react")
