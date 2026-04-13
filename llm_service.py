import tiktoken
from pydantic import BaseModel
from openai import AsyncOpenAI
import config
from prompts import PROMPTS
from logger import get_logger

logger = get_logger(__name__)

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# [OPT-1] 初始化 tiktoken encoder，用於計算 token 數量
_tokenizer = tiktoken.get_encoding("cl100k_base")
_HISTORY_TOKEN_BUDGET = 2500  # 留下足够空間給 RAG context 和回答

def _trim_history_to_budget(history: list, budget: int = _HISTORY_TOKEN_BUDGET) -> list:
    """
    [OPT-1] 將對話歷史中超出 token 預算的早期訊息逐一刪除，
    避免最後 8 條訊息加起來超出模型 context window 造成 API 失敗。
    策略：從case 最新的訊息開始往前填，直到超出預算為止。
    """
    selected = []
    total_tokens = 0
    for msg in reversed(history):
        text = f"{msg.get('role', '')}: {msg.get('content', '')}"
        tokens = len(_tokenizer.encode(text))
        if total_tokens + tokens > budget:
            break
        selected.append(msg)
        total_tokens += tokens
    return list(reversed(selected))

async def _translate_to_zh(text: str) -> str:
    """
    將問題翻譯成繁體中文，供 BM25 Sparse Search 與 Cross-Encoder 使用。
    當使用者以英文提問，但知識庫為中文時，此翻譯能大幅提升語意相似度。
    若翻譯失敗則 fallback 回原文。
    """
    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": (
                    "You are a professional translator. "
                    "Translate the user's text into Traditional Chinese (繁體中文). "
                    "Output ONLY the translated text, no explanations."
                )},
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            max_tokens=300,
        )
        translated = response.choices[0].message.content.strip()
        logger.info(f"[Translate] '{text}' → '{translated}'")
        return translated
    except Exception as e:
        logger.warning(f"[Translate] Translation failed ({type(e).__name__}): {e}. Using original query.")
        return text

async def _rephrase_question_with_history(history: list, question: str, lang: str = 'zh') -> str:
    """
    使用對話歷史來重構一個新的、獨立的問題。
    """
    if not history:
        return question

    # [OPT-1] 動態截取歷史，确保不超出 token 預算
    trimmed_history = _trim_history_to_budget(history)
    if not trimmed_history:
        # 即便是最新一條訊息也超出預算，直接回傳原問題
        return question
    history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in trimmed_history])
    system_prompt = PROMPTS[lang]['rephrase_system']
    user_prompt = PROMPTS[lang]['rephrase_user'].format(history_str=history_str, question=question)

    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=150,
        )
        rephrased_question = response.choices[0].message.content.strip()
        if not rephrased_question:
            return question
        # 📝 INFO：記錄問題重構成功
        logger.info(f"[Rephrase] Successfully rephrased question: {rephrased_question}")
        return rephrased_question
    except Exception as e:
        # ⚠️ WARNING：問題重構失敗
        logger.warning(f"[Rephrase] Failed to rephrase question: {e}", exc_info=True)
        return question

class SuggestedReplies(BaseModel):
    replies: list[str]

async def generate_suggested_replies(question: str, context_text: str, lang: str = 'zh') -> list[str]:
    system_prompt = (
        "You are a helpful assistant predicting the user's next questions. Rules:\n"
        "1. Generate exactly 3 short follow-up questions (under 15 words each) based on the provided reference context.\n"
        "2. If the context mentions specific scholarships, the questions MUST target those specific scholarships by name (e.g., 'What is the exact deadline for Scholarship X?').\n"
        "3. DO NOT generate broad or generic questions.\n"
        "4. CRITICAL: DO NOT ask questions that the bot cannot answer, such as asking for someone's personal email, direct phone number, or physical office address."
    )
    if lang == 'zh':
        system_prompt = (
            "你是一個預測使用者意圖的貼心助教。請根據使用者的問題以及檢索到的「參考資料(Context)」，產生 3 個使用者接下來最可能追問的「短問題」。\n"
            "【嚴格規則】\n"
            "1. 每個問題必須極度簡短且口語（15字以內）。\n"
            "2. 如果參考資料中提到了多項獎學金，請**挑其中一個最有代表性的獎學金**名稱來發問（例如：「ＯＯ獎學金的申請表在哪裡下載？」），絕對不要問籠統廣泛的問題（例如：「有哪些推薦的獎學金？」）。\n"
            "3. **絕對不可以**問「機器人無法回答的問題」，例如：承辦人的信箱是什麼？全球處的地址在哪裡？聯絡電話是幾號？（因為隱私關係，知識庫通常缺乏這些聯絡細節）。\n"
            "4. 建議詢問：該獎學金的應備文件、申請資格細節、或是截止日期。"
        )
    
    try:
        response = await openai_client.beta.chat.completions.parse(
            model=config.OPENAI_MODEL_NAME,  # [OPT-2] 使用 config 而非硬編碼 "gpt-4o-mini"
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User's incoming question: {question}\n\nReference Context:\n{context_text}"}
            ],
            response_format=SuggestedReplies,
            temperature=0.7,
        )
        return response.choices[0].message.parsed.replies
    except Exception as e:
        # ⚠️ WARNING：根據使用者的問答預測產生的3個問題失敗了
        logger.warning(f"[Rephrase] Failed to predict follow-up questions: {e}", exc_info=True)
        return []
