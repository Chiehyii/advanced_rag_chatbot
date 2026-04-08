import json
import os 
import sys
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from openai import AsyncOpenAI
import config
from prompts import PROMPTS

# 加上這行以便 standalone 執行時可以讀到 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [BUG-6] 引入 logger，取代 print()
from logger import get_logger
logger = get_logger(__name__)

# --- 1. 定義 Pydantic 模型 (雙效合一) ---
class FilterGroup(BaseModel):
    field: Literal['identity', 'education_system', 'tags'] = Field(
        description="The metadata field to filter on."
    )
    operator: Literal['ARRAY_CONTAINS', 'ARRAY_CONTAINS_ANY', 'ARRAY_CONTAINS_ALL'] = Field(
        description="The Milvus array operator. Use ARRAY_CONTAINS for a single value. Use ARRAY_CONTAINS_ANY for OR logic between multiple values. Use ARRAY_CONTAINS_ALL for AND logic between multiple values."
    )
    values: List[str] = Field(
        description="The list of EXACT valid values from the schema to filter by."
    )

class ScholarshipFilters(BaseModel):
    conditions: List[FilterGroup] = Field(
        default_factory=list, 
        description="List of filtering conditions to apply."
    )
    global_logic: Literal['AND', 'OR'] = Field(
        default='AND', 
        description="The logical operator used to combine the different condition groups."
    )

# ⭐️ 核心：讓 LLM 同時回傳 intent 和 filters
class QueryAnalysis(BaseModel):
    intent: str = Field(
        description="The classified intent of the user's question. Must be one of the defined intent keys."
    )
    filters: Optional[ScholarshipFilters] = Field(
        default=None,
        description="Extract filters ONLY IF the intent is 'scholarship' AND there are specific constraints. Otherwise leave empty."
    )

# --- 2. Schema 快取機制 ---
_SCHEMA_CACHE = None
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata_schema.json")

def get_metadata_schema():
    """安全的取得 metadata_schema.json 的內容並暫存在記憶體中"""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        try:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                _SCHEMA_CACHE = json.load(f)
        except Exception as e:
            # [BUG-6] 改用 logger 取代 print，統一記錄到日誌系統
            logger.error(f"[Schema] Schema 載入失敗: {e}", exc_info=True)
            _SCHEMA_CACHE = {
                "identity": [],
                "education_system": [],
                "tags": []
            }
    return _SCHEMA_CACHE

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# --- 3. 核心分析函數 ---
async def analyze_query(question: str, lang: str = 'zh') -> tuple[str, str]:
    """
    一次呼叫 OpenAI，同時完成「意圖分類」與「Milvus 過濾條件提取」。
    回傳值: (intent字串, milvus_expr字串)
    """
    metadata_schema = get_metadata_schema()
    intent_definitions = PROMPTS[lang]['intent_definitions']
    # 從 INTENT_DEFINITIONS 動態生成提示選項
    intent_options = "\n".join([f"- '{name}': {desc}" for name, desc in intent_definitions.items()])

    system_prompt = f"""
    You are an expert AI routing and filtering assistant.
    Your task is to analyze the user's query and do TWO things:
    
    TASK 1: Intent Classification
    Classify the query into EXACTLY ONE of the following intent categories:
    {intent_options}
    If none match, classify as 'other'.

    TASK 2: Scholarship Filtering (ONLY if intent is 'scholarship')
    Extract filtering criteria from the user's query based EXACTLY on these valid choices:
    - Valid Identities: {json.dumps(metadata_schema.get('identity', []), ensure_ascii=False)}
    - Valid Education Systems: {json.dumps(metadata_schema.get('education_system', []), ensure_ascii=False)}
    - Valid Tags: {json.dumps(metadata_schema.get('tags', []), ensure_ascii=False)}
    
    Rules for Filtering:
    1. Only use EXACT matches from the valid lists above.
    2. If the user does not specify a constraint for a category, DO NOT invent one.
    """

    try:
        completion = await openai_client.beta.chat.completions.parse(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            response_format=QueryAnalysis,
            temperature=0.0
        )
        
        parsed_result = completion.choices[0].message.parsed
        if not parsed_result:
            return "other", ""
            
        intent = parsed_result.intent.lower()
        if intent not in intent_definitions:
            intent = "other"
            
        # 如果意圖不是 scholarship，或者沒有過濾條件，直接回傳空 expr
        if intent != "scholarship" or not parsed_result.filters or not parsed_result.filters.conditions:
            return intent, ""

        # 組裝 Milvus expr
        expr_parts = []
        for group in parsed_result.filters.conditions:
            if group.field not in metadata_schema:
                continue
            valid_vals = [v for v in group.values if v in metadata_schema[group.field]]
            if not valid_vals:
                continue
                
            if group.operator == 'ARRAY_CONTAINS':
                expr_parts.append(f'(ARRAY_CONTAINS({group.field}, "{valid_vals[0]}") or ARRAY_LENGTH({group.field}) == 0)')
            elif group.operator in ['ARRAY_CONTAINS_ANY', 'ARRAY_CONTAINS_ALL']:
                vals_str = ", ".join([f'"{v}"' for v in valid_vals])
                expr_parts.append(f'({group.operator}({group.field}, [{vals_str}]) or ARRAY_LENGTH({group.field}) == 0)')
                
        if expr_parts:
            join_str = f" {parsed_result.filters.global_logic} "
            expr = join_str.join([f"({part})" for part in expr_parts])
            return intent, expr
            
        return intent, ""
        
    except Exception as e:
        # [BUG-6] 改用 logger 精確記錄錯誤，並向上傳播讓呼叫端知道 API 失敗
        # 注意：不要靜默回傳 ('other', '')，否則使用者問獎學金問題卻收到 Small Talk 回覆
        logger.error(f"[Query Analyzer] analyze_query failed: {type(e).__name__}: {e}", exc_info=True)
        raise  # 讓 stream_chat_pipeline 接住並決定如何處理