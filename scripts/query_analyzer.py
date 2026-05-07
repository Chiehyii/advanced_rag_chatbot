import json
import os 
import sys
from pydantic import BaseModel, Field
from typing import Literal
from openai import AsyncOpenAI
import config
from prompts import PROMPTS

# 加上這行以便 standalone 執行時可以讀到 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [BUG-6] 引入 logger，取代 print()
from logger import get_logger
logger = get_logger(__name__)


# --- Pydantic Model: 純意圖分類 ---
class QueryAnalysis(BaseModel):
    intent: str = Field(
        description="The classified intent of the user's question. Must be one of the defined intent keys."
    )


openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


# --- 核心分析函數（簡化版：僅意圖分類）---
async def analyze_query(question: str, lang: str = 'zh') -> str:
    """
    呼叫 OpenAI 進行意圖分類。
    過濾條件的生成已移至 LangGraph 的 retrieve_node，
    基於跨輪次累積的 user_profile 動態產生。

    回傳值: intent 字串 ("scholarship" 或 "other")
    """
    intent_definitions = PROMPTS[lang]['intent_definitions']
    intent_options = "\n".join([f"- '{name}': {desc}" for name, desc in intent_definitions.items()])

    system_prompt = PROMPTS[lang]['query_analyzer_system'].format(
        intent_options=intent_options,
    )

    try:
        completion = await openai_client.beta.chat.completions.parse(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            max_completion_tokens=200,
            response_format=QueryAnalysis,
            temperature=0.0
        )
        
        parsed_result = completion.choices[0].message.parsed
        if not parsed_result:
            return "other"
            
        intent = parsed_result.intent.lower()
        if intent not in intent_definitions:
            intent = "other"
        
        logger.info(f"[Query Analyzer] Intent classified: {intent}")
        return intent
        
    except Exception as e:
        logger.error(f"[Query Analyzer] analyze_query failed: {type(e).__name__}: {e}", exc_info=True)
        raise  # 讓呼叫端決定如何處理