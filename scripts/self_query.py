import json
import os
import sys
from pydantic import BaseModel, Field
from typing import List, Optional
from openai import AsyncOpenAI

# 加上這行以便 standalone 執行時可以讀到 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


from typing import List, Literal, Optional

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

# 讀取 Schema 作為 LLM 的參考
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata_schema.json")
_SCHEMA_CACHE = None

def get_metadata_schema():
    """安全的取得 metadata_schema.json 的內容並暫存在記憶體中"""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        try:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                _SCHEMA_CACHE = json.load(f)
        except Exception as e:
            # 🚨 ERROR：Schema 載入失敗
            print(f"[Schema] Schema 載入失敗: {e}")
            # 載入失敗時，回傳空字典，避免後續程式出錯
            _SCHEMA_CACHE = {
                "identity": [],
                "education_system": [],
                "tags": []
            }
    return _SCHEMA_CACHE

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

async def generate_milvus_expr(question: str) -> str:
    """
    透過 OpenAI Structured Outputs，分析用戶問題並產生針對 Milvus 的 Metadata Filter Expression (expr)。
    只嚴格回傳那些"確定存在於問句中且對應到 metadata_schema.json"的條件。
    如果問句沒有任何限制條件，則回傳空字串 ""。
    """

    # 把記憶體裡面的 schema 拿出來用
    metadata_schema = get_metadata_schema()
    
    system_prompt = f"""
    You are an AI assistant that extracts filtering criteria from a user's query about scholarships.
    You must map the user's situation to the EXACT terms provided in the valid choices below.
    If the user does not specify a constraint for a category, leave the conditions empty. Do NOT guess.
    
    Valid Identities: {json.dumps(metadata_schema['identity'], ensure_ascii=False)}
    Valid Education Systems: {json.dumps(metadata_schema['education_system'], ensure_ascii=False)}
    Valid Tags: {json.dumps(metadata_schema['tags'], ensure_ascii=False)}
    
    Rules for output:
    1. Only use EXACT matches from the valid lists above.
    2. ARRAY_CONTAINS takes exactly 1 value. ARRAY_CONTAINS_ANY acts like OR. ARRAY_CONTAINS_ALL acts like AND.
    3. Example 1: User says "我是泰雅族的大二生" 
       -> conditions=[{{field: 'identity', operator: 'ARRAY_CONTAINS', values: ['原住民']}}, {{field: 'education_system', operator: 'ARRAY_CONTAINS', values: ['大學部']}}], global_logic: 'AND'
    4. Example 2: User says "有哪些給低收或中低收的補助？"
       -> conditions=[{{field: 'identity', operator: 'ARRAY_CONTAINS_ANY', values: ['低收入戶', '中低收入戶']}}], global_logic: 'AND'
    5. Example 3: User says "能出國交換且有志工服務的獎學金"
       -> conditions=[{{field: 'tags', operator: 'ARRAY_CONTAINS_ALL', values: ['海外交流', '志工服務']}}], global_logic: 'AND'
    """
    
    try:
        completion = await openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            response_format=ScholarshipFilters,
            temperature=0.0
        )
        
        parsed_filters = completion.choices[0].message.parsed
        if not parsed_filters or not parsed_filters.conditions:
            return ""
            
        expr_parts = []
        for group in parsed_filters.conditions:
            # Validate field and values against schema
            if group.field not in metadata_schema:
                continue
                
            valid_vals = [v for v in group.values if v in metadata_schema[group.field]]
            if not valid_vals:
                continue
                
            if group.operator == 'ARRAY_CONTAINS':
                # Force to use only the first valid value for single contains
                # Also match documents where the array is empty (meaning universally applicable)
                expr_parts.append(
                    f'(ARRAY_CONTAINS({group.field}, "{valid_vals[0]}") or ARRAY_LENGTH({group.field}) == 0)'
                )
            elif group.operator in ['ARRAY_CONTAINS_ANY', 'ARRAY_CONTAINS_ALL']:
                vals_str = ", ".join([f'"{v}"' for v in valid_vals])
                # Also match documents where the array is empty (meaning universally applicable)
                expr_parts.append(
                    f'({group.operator}({group.field}, [{vals_str}]) or ARRAY_LENGTH({group.field}) == 0)'
                )
                
        if expr_parts:
            # Join multiple condition groups using the specified global logic
            join_str = f" {parsed_filters.global_logic} "
            # Wrap each part in parentheses to ensure safe logic precedence
            expr = join_str.join([f"({part})" for part in expr_parts])
            return expr
            
        return ""
        
    except Exception as e:
        # 🚨 ERROR：生成 expr 失敗
        print(f"[Self-Query] Error generating expr: {e}")
        return ""

# For testing
if __name__ == "__main__":
    import asyncio
    async def test():
        q1 = "我是低收入戶的大學部原住民學生，想找不用還的獎學金"
        expr1 = await generate_milvus_expr(q1)
        print(f"Q: {q1}\nExpr: {expr1}\n")
        
        q2 = "介紹一下慈濟的獎學金"
        expr2 = await generate_milvus_expr(q2)
        print(f"Q: {q2}\nExpr: {expr2}\n")
        
    asyncio.run(test())
