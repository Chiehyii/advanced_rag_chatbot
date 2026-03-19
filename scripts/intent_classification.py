import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from openai import AsyncOpenAI
from prompts import PROMPTS
from pydantic import BaseModel, Field # 1. 引入 Pydantic 模組，定義資料結構

# 建立 OpenAI client
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# 2. 建立 Pydantic 模型，定義我們期望 LLM 回傳的資料結構
class IntentResult(BaseModel):
    intent: str = Field(
        description="The classified intent of the user's question. Must be one of the defined intent keys."
    )

async def intent_classification(question: str, lang: str = 'zh') -> str:
    """
    輸入問題，輸出意圖分類。
    使用 OpenAI Structured Outputs 確保回傳格式穩定。
    """
    
    intent_definitions = PROMPTS[lang]['intent_definitions']
    
    # 從 INTENT_DEFINITIONS 動態生成提示選項
    intent_options = "\n".join([f"- '{name}': {desc}" for name, desc in intent_definitions.items()])
    
    system_prompt = f"""
    You are an AI assistant that classifies the user's intent.
    You must classify the user's question into EXACTLY ONE of the following intent categories:
    
    {intent_options}
    
    If none of the categories match, or if it is just a casual greeting, you must classify it as 'other'.
    """

    try:
        # 3.改用 beta.chat.completions.parse 來強制輸出 JSON 結構
        response = await client.beta.chat.completions.parse(
            model=config.OPENAI_MODEL_NAME, # 建議使用 gpt-4o-mini 或 gpt-4o
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            response_format=IntentResult, # 指定剛剛建立的 Pydantic 模型
            temperature=0.0 # 意圖分類不需要創意，設為 0
        )

        # 4. 透過 .parsed 安全地取得結果
        parsed_result = response.choices[0].message.parsed
        if parsed_result:
            intent = parsed_result.intent.lower()
        else:
            intent = "other"
    except Exception as e:
        print(f"[Error] Intent classification failed: {e}")
        intent = "other"

    # 最後的安全檢查：確保 LLM 給的 intent 真的是我們有定義的
    if intent not in intent_definitions:
        intent = "other"
    return intent