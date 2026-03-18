import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from openai import AsyncOpenAI
from prompts import PROMPTS

# 建立 OpenAI client
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

async def intent_classification(question: str, lang: str = 'zh') -> str:
    """
    輸入問題，輸出意圖分類。
    意圖類別從 INTENT_DEFINITIONS 動態生成。
    """
    
    intent_definitions = PROMPTS[lang]['intent_definitions']
    
    # 從 INTENT_DEFINITIONS 動態生成提示選項
    intent_options = "\n".join([f"{i+1}. {name} → {desc}" for i, (name, desc) in enumerate(intent_definitions.items())])
    
    prompt = PROMPTS[lang]['intent_prompt'].format(
        intent_options=intent_options,
        question=question
    )

    resp = await client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    intent = resp.choices[0].message.content.strip().lower()

    # 從 INTENT_DEFINITIONS 的鍵來做安全檢查，如果都不是，就預設為 "other"
    if intent not in intent_definitions:
        intent = "other"

    return intent