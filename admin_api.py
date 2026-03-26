import os
import re
import uuid
import json
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import psycopg2
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient, DataType, Function, FunctionType
import config
import hashlib
from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext

router = APIRouter(prefix="/api", tags=["admin"])
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

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
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
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
        if username is None or username != config.ADMIN_USERNAME:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    return username

# --- Helper functions ---
def get_db_connection():
    """[SEC-3] 從共用連線池借用連線，避免每次請求都建立新連線。"""
    if not config.DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool is not available.")
    return config.DB_POOL.getconn()

def release_db_connection(conn):
    """[SEC-3] 將連線歸還連線池。必須在 finally 區塊中呼叫。"""
    if conn and config.DB_POOL:
        config.DB_POOL.putconn(conn)


def emb_text(text: str):
    return (
        openai_client.embeddings.create(input=text, model=config.EMBEDDING_MODEL)
        .data[0]
        .embedding
    )

def _get_hash_if_url(url: str):
    if not url: return None, None
    try:
        resp = requests.get(url, timeout=10)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.content, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        return hashlib.md5(text.encode('utf-8')).hexdigest(), datetime.now(timezone.utc).isoformat()
    except Exception as e:
        print(f"Failed to get hash for {url}: {e}")
        return None, None

def init_milvus_collection():
    """Initializes the collection if it doesn't exist, similar to rag-web-source2-hybrid.py"""
    milvus_client = MilvusClient(
        uri=config.CLUSTER_ENDPOINT,
        token=config.ZILLIZ_API_KEY,
    )
    collection_name = config.MILVUS_COLLECTION

    if milvus_client.has_collection(collection_name):
        return milvus_client, collection_name

    print(f"Collection {collection_name} non-existent, creating it...")
    schema = milvus_client.create_schema(
        auto_id=False,
        enable_dynamic_field=True
    )
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("text", DataType.VARCHAR, max_length=5000, enable_analyzer=True)
    schema.add_field("source_file", DataType.VARCHAR, max_length=256)
    schema.add_field("source_path", DataType.VARCHAR, max_length=2048)
    schema.add_field("source_url", DataType.VARCHAR, max_length=200)
    schema.add_field("identity", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("education_system", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("category", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("tags", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=200, max_length=200, nullable=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=1536)
    schema.add_field("text_sparse", DataType.SPARSE_FLOAT_VECTOR, description="Sparse vector")

    bm25_function = Function(
        name="text_bm25_emb",
        input_field_names=["text"],
        output_field_names=["text_sparse"],
        function_type=FunctionType.BM25,
    )
    schema.add_function(bm25_function)

    milvus_client.create_collection(
        collection_name=collection_name,
        schema=schema,
        consistency_level="Bounded"
    )

    index_params = milvus_client.prepare_index_params()
    index_params.add_index(
        field_name="vector", index_name="vector_index", 
        index_type="AUTOINDEX", metric_type="COSINE"
    )
    index_params.add_index(
        field_name="text_sparse", index_name="text_sparse_index",
        index_type="SPARSE_INVERTED_INDEX", metric_type="BM25",
        params={"inverted_index_algo": "DAAT_MAXSCORE"}
    )
    milvus_client.create_index(collection_name=collection_name, index_params=index_params)
    milvus_client.load_collection(collection_name=collection_name)
    
    return milvus_client, collection_name

# --- Endpoints ---

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != config.ADMIN_USERNAME or form_data.password != config.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": config.ADMIN_USERNAME}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT scholarship_code, title, link, category, created_at, education_system, tags, identity FROM scholarships ORDER BY created_at DESC;")
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
            })
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

@router.get("/scholarships/{scholarship_code}")
def get_scholarship(scholarship_code: str, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT scholarship_code, title, link, category, education_system, tags, identity, amount_summary, description, application_date_text, contact, markdown_content FROM scholarships WHERE scholarship_code = %s;", (scholarship_code,))
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
            "markdown_content": row[11]
        }
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

@router.post("/extract_info")
def extract_scholarship_info(request: ExtractRequest, current_admin: str = Depends(verify_admin)):
    if not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Must provide either 'url' or 'text'")
    
    content_to_process = ""
    
    if request.url:
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
        
    system_prompt = """
    你是一個獎學金資訊擷取的專家助理。請從收到的內容中提取所需的資訊並以 JSON 格式回傳。
    請提取以下欄位：
    - title (名稱)
    - link (網址 - 若內容有提供的話)
    - category (衣珠類別，例如: "生活無憂", 如果沒有請寫 "")
    - education_system (學制：陣列，例如 ["大學部", "研究所"])
    - tags (類別/種類：陣列，例如 ["減免", "助學金"])
    - identity (身分：陣列，例如 ["中低收入戶", "低收入戶", "原住民"])
    - amount_summary (金額說明)
    - description (介紹 - 簡要描述)
    - application_date_text (申請日期)
    - contact (聯絡人)
    - markdown_content (請把所有資訊整理成一篇詳細的 Markdown 文章，用於存入知識庫。文章應該包含所有重要細節與資格條件)
    
    回傳的 JSON 需要包含上述 key 值。不要回傳 markdown 代碼塊格式，只需回傳合法的 JSON 字串。
    """
    
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
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post("/scholarships")
def save_scholarship(form: ScholarshipForm, current_admin: str = Depends(verify_admin)):
    # 1. Save to PostgreSQL
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        cursor.execute(insert_query, (
            form.scholarship_code, form.title, form.link, form.category,
            json.dumps(form.education_system, ensure_ascii=False),
            json.dumps(form.tags, ensure_ascii=False),
            json.dumps(form.identity, ensure_ascii=False),
            form.amount_summary, form.description, form.application_date_text,
            form.contact, form.markdown_content, new_hash, current_time
        ))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

    # 2. Insert vector chunks into Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(form.markdown_content)
        
        data_to_insert = []
        for chunk in chunks:
            if not chunk.strip(): continue
            
            chunk_id = random.randint(1, 9223372036854775806) # Big integer for 64-bit ID
            
            data_to_insert.append({
                "id": chunk_id,
                "text": chunk.strip(),
                "source_file": form.title + ".md",
                "source_path": form.scholarship_code, # Use code as path indicator
                "source_url": form.link or "",
                "identity": form.identity,
                "education_system": form.education_system,
                "category": [form.category] if form.category else [],
                "tags": form.tags,
                "vector": emb_text(chunk.strip())
            })
            
        if data_to_insert:
            insert_result = milvus_client.insert(collection_name=collection_name, data=data_to_insert)
            milvus_client.flush(collection_name=collection_name)
            
        return {"status": "success", "message": f"Saved {len(data_to_insert)} chunks to Knowledge Base"}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Vector DB Error: {str(e)}")

@router.put("/scholarships/{scholarship_code}")
def update_scholarship(scholarship_code: str, form: ScholarshipForm, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]
    # This acts very similarly to save_scholarship but handles Milvus cleanup first
    
    # 1. Save to PostgreSQL
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        new_hash, current_time = _get_hash_if_url(form.link)
        
        update_query = """
        UPDATE scholarships SET
            title = %s, link = %s, category = %s, education_system = %s, tags = %s, identity = %s,
            amount_summary = %s, description = %s, application_date_text = %s, contact = %s, 
            markdown_content = %s, content_hash = %s, last_checked_at = %s
        WHERE scholarship_code = %s;
        """
        
        cursor.execute(update_query, (
            form.title, form.link, form.category,
            json.dumps(form.education_system, ensure_ascii=False),
            json.dumps(form.tags, ensure_ascii=False),
            json.dumps(form.identity, ensure_ascii=False),
            form.amount_summary, form.description,
            form.application_date_text, form.contact, form.markdown_content,
            new_hash, current_time, scholarship_code
        ))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

    # 2. Re-Insert vector chunks into Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        
        # Delete old chunks
        milvus_client.delete(
            collection_name=collection_name,
            filter=f"source_path == '{scholarship_code}'"
        )
        # It's important to flush after delete so reads don't see deleted data
        milvus_client.flush(collection_name=collection_name)
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(form.markdown_content)
        
        data_to_insert = []
        for chunk in chunks:
            if not chunk.strip(): continue
            chunk_id = random.randint(1, 9223372036854775806)
            data_to_insert.append({
                "id": chunk_id,
                "text": chunk.strip(),
                "source_file": form.title + ".md",
                "source_path": scholarship_code,
                "source_url": form.link or "",
                "identity": form.identity,
                "education_system": form.education_system,
                "category": [form.category] if form.category else [],
                "tags": form.tags,
                "vector": emb_text(chunk.strip())
            })
            
        if data_to_insert:
            milvus_client.insert(collection_name=collection_name, data=data_to_insert)
            milvus_client.flush(collection_name=collection_name)
            
        return {"status": "success", "message": f"Updated {len(data_to_insert)} chunks in Knowledge Base"}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Vector DB Error: {str(e)}")

@router.delete("/scholarships/{scholarship_code}")
def delete_scholarship(scholarship_code: str, current_admin: str = Depends(verify_admin)):
    scholarship_code = validate_scholarship_code(scholarship_code)  # [SEC-2]
    # 1. Delete from PostgreSQL
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scholarships WHERE scholarship_code = %s", (scholarship_code,))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

    # 2. Delete from Milvus
    try:
        milvus_client, collection_name = init_milvus_collection()
        milvus_client.delete(
            collection_name=collection_name,
            filter=f"source_path == '{scholarship_code}'"
        )
        milvus_client.flush(collection_name=collection_name)
        return {"status": "success", "message": "Successfully deleted from DB and Knowledge Base"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Vector DB Error: {str(e)}")

