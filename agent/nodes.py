# -*- coding: utf-8 -*-
"""
Agent Nodes
===========
每個函式對應 StateGraph 中的一個節點。
所有 Node 接收 AgentState、回傳部分更新（Partial State Update）。
所有 Prompt 統一從 prompts.py 讀取，不在此檔案中硬寫。
"""
from __future__ import annotations
import json
from openai import AsyncOpenAI
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from typing import Literal, Optional

import config
from agent.state import AgentState, UserProfile
from prompts import PROMPTS
from db_repository import clean_retrieved_contexts
from rag_service import get_embedding, retrieve_context
from logger import get_logger

logger = get_logger(__name__)

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


def _usage_to_dict(usage) -> dict | None:
    if not usage:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens or 0,
        "completion_tokens": usage.completion_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }


def _safe_milvus_literal(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 80:
        return None
    if any(ord(ch) < 32 for ch in cleaned):
        return None
    if any(ch in cleaned for ch in ['"', "\\", "[", "]", "(", ")", ";"]):
        return None
    return cleaned


def _quote_milvus_literal(value: object) -> str | None:
    cleaned = _safe_milvus_literal(value)
    if cleaned is None:
        return None
    return '"' + cleaned + '"'


def _detect_language(text: str) -> str:
    """簡易語言偵測：ASCII 字元佔比 > 70% 視為英文，否則視為中文。"""
    if not text:
        return "zh"
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    ratio = ascii_chars / len(text)
    return "en" if ratio > 0.7 else "zh"


# ─────────────────────────────────────────
# Pydantic model for structured extraction
# ─────────────────────────────────────────
class ExtractedProfile(BaseModel):
    """LLM 從對話中同時判斷意圖並萃取使用者條件"""
    intent: Literal["scholarship", "small_talk"] = Field(
        description="使用者意圖：scholarship（獎助學金相關）或 small_talk（閒聊/問候/道謝）"
    )
    education_system: Optional[str] = Field(None, description="學制，例如 大學部 / 碩士班 / 博士班 / 五專 / 二技")
    nationality: Optional[str] = Field(None, description="國籍，例如 本國籍 / 外籍生 / 僑生 / 港澳生")
    registered_residence: Optional[str] = Field(None, description="戶籍地，例如 臺北市 / 花蓮縣 / 不限")
    identity: Optional[list[str]] = Field(None, description="身分，例如 ['低收入戶', '原住民']")
    need: Optional[str] = Field(None, description="需求，例如 生活補助 / 海外交流 / 急難救助")
    specific_name: Optional[str] = Field(None, description="使用者指定的獎學金名稱")
    is_sufficient: bool = Field(False, description="條件是否足夠（需要 nationality + education_system，或 specific_name）")


# ─────────────────────────────────────────
# Node 1: Analyze & Extract（意圖+條件萃取合一）
# ─────────────────────────────────────────
async def analyze_and_extract_node(state: AgentState) -> dict:
    """
    一次 LLM 呼叫，同時完成：
    1. 意圖分類（scholarship vs small_talk）
    2. 條件萃取（education_system, nationality, identity 等）
    
    取代了原本的 intent_router_node + profile_extraction_node。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    existing_profile = state.get("user_profile", {})
    title_filter = state.get("title_filter")

    # 如果前端有帶 title_filter，直接走 scholarship，跳過 LLM
    if title_filter and len(title_filter) > 0:
        logger.info(f"[Analyze] Title filter detected: {title_filter} → scholarship, sufficient=True")
        return {
            "current_intent": "scholarship",
            "user_profile": existing_profile,
            "_profile_sufficient": True,
            "_usage": None,
        }

    # 把 messages 序列化為文字
    history_text = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history_text += f"user: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history_text += f"assistant: {msg.content}\n"

    system_prompt = PROMPTS[lang]['profile_extraction_system']

    try:
        completion = await openai_client.beta.chat.completions.parse(
            model=config.OPENAI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"對話歷史:\n{history_text}"},
            ],
            response_format=ExtractedProfile,
            temperature=0.0,
            max_completion_tokens=500,
        )
        extracted = completion.choices[0].message.parsed
        if not extracted:
            logger.warning("[Analyze] Extraction returned None, defaulting to scholarship.")
            return {
                "current_intent": "scholarship",
                "user_profile": existing_profile,
                "_profile_sufficient": False,
                "_usage": _usage_to_dict(completion.usage),
            }

        # 設定意圖
        intent = extracted.intent
        logger.info(f"[Analyze] Intent={intent}, is_sufficient={extracted.is_sufficient}")

        # 如果是 small_talk，不需要更新 profile
        if intent == "small_talk":
            return {
                "current_intent": "small_talk",
                "user_profile": existing_profile,
                "_profile_sufficient": False,
                "_usage": _usage_to_dict(completion.usage),
            }

        # scholarship：合併到現有 profile（新值覆蓋舊值，但不清除舊的）
        new_profile: UserProfile = {**existing_profile}
        if extracted.education_system:
            new_profile["education_system"] = extracted.education_system
        if extracted.nationality:
            new_profile["nationality"] = extracted.nationality
        if extracted.registered_residence:
            new_profile["registered_residence"] = extracted.registered_residence
        if extracted.identity:
            new_profile["identity"] = extracted.identity
        if extracted.need:
            new_profile["need"] = extracted.need
        if extracted.specific_name:
            new_profile["specific_name"] = extracted.specific_name

        logger.info(f"[Analyze] Profile extracted with fields: {sorted(new_profile.keys())}")
        return {
            "current_intent": "scholarship",
            "user_profile": new_profile,
            "_profile_sufficient": extracted.is_sufficient,
            "_usage": _usage_to_dict(completion.usage),
        }

    except Exception as e:
        logger.error(f"[Analyze] Failed: {e}", exc_info=True)
        return {
            "current_intent": "scholarship",
            "user_profile": existing_profile,
            "_profile_sufficient": False,
            "_usage": None,
        }


# ─────────────────────────────────────────
# Utility: Profile → Milvus Expression
# ─────────────────────────────────────────
def build_milvus_expr_from_profile(profile: dict, title_filter: list[str] | None = None) -> str:
    """
    根據跨輪次累積的 user_profile，動態生成精確的 Milvus 過濾表達式。

    過濾規則：
    - registered_residence: 使用者戶籍 OR "不限"
    - nationality: 精確匹配
    - education_system: 精確匹配
    - identity: 使用者身分 OR "一般生"
    """
    if title_filter and len(title_filter) > 0:
        safe_titles = []
        for title in title_filter[:3]:
            quoted = _quote_milvus_literal(f"{title}.md")
            if quoted:
                safe_titles.append(quoted)
        if not safe_titles:
            logger.warning("[Filter] Title filter values rejected by validation.")
            return ""
        title_exprs = ", ".join(safe_titles)
        expr = f"source_file in [{title_exprs}]"
        logger.info(f"[Filter] Title filter override: {expr}")
        return expr

    parts = []

    safe_profile = {}
    for key in ("registered_residence", "nationality", "education_system"):
        safe_value = _safe_milvus_literal(profile.get(key))
        if safe_value:
            safe_profile[key] = safe_value
    identities = profile.get("identity")
    if isinstance(identities, list):
        safe_profile["identity"] = [
            safe_value for safe_value in (_safe_milvus_literal(v) for v in identities) if safe_value
        ]
    profile = safe_profile

    residence = profile.get("registered_residence")
    if residence and residence != "不限":
        parts.append(
            f'(ARRAY_CONTAINS(registered_residence, "{residence}") or '
            f'ARRAY_CONTAINS(registered_residence, "不限"))'
        )

    nationality = profile.get("nationality")
    if nationality:
        parts.append(f'ARRAY_CONTAINS(nationality, "{nationality}")')

    edu = profile.get("education_system")
    if edu:
        parts.append(f'ARRAY_CONTAINS(education_system, "{edu}")')

    identities = profile.get("identity")
    if identities and isinstance(identities, list):
        # 畢業生是獨立身分，不應同時匹配一般生的獎學金
        # 其他特殊身分（如低收入戶、原住民）仍然可以申請一般生的獎學金
        has_graduate = "畢業生" in identities
        special_ids = [i for i in identities if i not in ("一般生", "畢業生")]
        if has_graduate and not special_ids:
            # 純畢業生：只搜尋畢業生獎學金
            parts.append('ARRAY_CONTAINS(identity, "畢業生")')
        elif special_ids:
            all_ids = special_ids + (["一般生"] if not has_graduate else [])
            if has_graduate:
                all_ids.append("畢業生")
            vals_str = ", ".join([f'"{v}"' for v in all_ids])
            parts.append(f'ARRAY_CONTAINS_ANY(identity, [{vals_str}])')
        else:
            parts.append('ARRAY_CONTAINS(identity, "一般生")')

    if parts:
        expr = " AND ".join([f"({p})" for p in parts])
        logger.info(f"[Filter] Profile-based expr: {expr}")
        return expr

    logger.info("[Filter] No profile conditions → no filter applied.")
    return ""


# ─────────────────────────────────────────
# Node 2: Retrieve（Milvus 檢索）
# ─────────────────────────────────────────
async def retrieve_node(state: AgentState) -> dict:
    """
    使用 Milvus 進行混合檢索。
    過濾條件由 build_milvus_expr_from_profile() 根據累積的 user_profile 動態生成。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    profile = state.get("user_profile", {})
    title_filter = state.get("title_filter")

    last_human = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    # 加入 profile 條件到檢索問題中，提升語意檢索精準度
    profile_parts = []
    if profile.get("education_system"):
        profile_parts.append(profile["education_system"])
    if profile.get("nationality"):
        profile_parts.append(profile["nationality"])
    if profile.get("identity"):
        if isinstance(profile["identity"], list):
            profile_parts.append("、".join(profile["identity"]))
        else:
            profile_parts.append(profile["identity"])
    if profile.get("need"):
        profile_parts.append(profile["need"])
    if profile.get("specific_name"):
        profile_parts.append(profile["specific_name"])

    if title_filter and len(title_filter) > 0:
        title_str = "、".join(title_filter[:3]) if lang == "zh" else ", ".join(title_filter[:3])
        prefix = f"關於「{title_str}」：" if lang == "zh" else f"Regarding '{title_str}': "
        search_question = prefix + last_human
    elif profile_parts:
        profile_str = "、".join(profile_parts)
        search_question = f"({profile_str}) {last_human}"
    else:
        search_question = last_human

    logger.info(f"[Retrieve] Search question prepared (length={len(search_question)})")

    expr = build_milvus_expr_from_profile(profile, title_filter)

    # 取得 embedding + 檢索（OpenAI Embedding 本身支援多語言，無需翻譯）
    try:
        embedding = await get_embedding(search_question)
        raw_docs = await retrieve_context(search_question, search_question, embedding, expr)
        cleaned = clean_retrieved_contexts(raw_docs)
        logger.info(f"[Retrieve] Found {len(cleaned)} documents after cleaning.")
        return {"retrieved_docs": cleaned}
    except Exception as e:
        logger.error(f"[Retrieve] Failed: {e}", exc_info=True)
        return {"retrieved_docs": []}


# ─────────────────────────────────────────
# Node 3: Generate RAG Answer（答案生成）
# ─────────────────────────────────────────
async def generate_node(state: AgentState) -> dict:
    """
    結合 user_profile + 檢索文件，生成最終 RAG 回答。
    根據 _profile_sufficient 旗標動態控制回答深度：
    - True: 完整表格+詳細資訊
    - False: 預覽摘要+溫柔反問
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    cleaned_contexts = state.get("retrieved_docs", [])
    profile = state.get("user_profile", {})
    profile_sufficient = state.get("_profile_sufficient", False)

    question = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            question = msg.content
            break

    # --- 組裝 context_for_llm ---
    from collections import defaultdict
    grouped = defaultdict(list)
    source_url_map = {}
    for c in cleaned_contexts:
        fname = c.get("source_file", "未知來源")
        grouped[fname].append(c.get("text", ""))
        if fname not in source_url_map and c.get("source_url"):
            source_url_map[fname] = c.get("source_url")

    distinct_source_count = len(grouped)
    context_for_llm = f"【系統資訊：本次共檢索到來自 {distinct_source_count} 個不同獎學金/補助來源的文件】\n"
    for idx, (fname, texts) in enumerate(grouped.items(), 1):
        title = fname.replace(".md", "").replace(".txt", "")
        url = source_url_map.get(fname, "")
        context_for_llm += f"\n---\n[文件 {idx}]\n來源名稱: {title}\n"
        if url:
            context_for_llm += f"來源網址: {url}\n"
        full_text = "\n".join(texts)
        context_for_llm += f"內容: {full_text}\n"

    # --- 組裝 system prompt（注入 profile_sufficient 旗標 + 語言指令）---
    question_lang = _detect_language(question)
    response_lang_instruction = (
        "\n\n⚠️ CRITICAL LANGUAGE RULE: The user asked in English. You MUST respond entirely in English, even though the context is in Chinese.\n"
        if question_lang == "en"
        else "\n\n⚠️ 關鍵語言規則：使用者使用中文提問，你必須全程使用繁體中文回答。\n"
    )

    system_prompt = PROMPTS[lang]["rag_system"].format(
        profile_sufficient=str(profile_sufficient)
    ) + response_lang_instruction

    if profile:
        profile_desc_parts = []
        if profile.get("education_system"):
            profile_desc_parts.append(f"學制: {profile['education_system']}")
        if profile.get("nationality"):
            profile_desc_parts.append(f"國籍: {profile['nationality']}")
        if profile.get("registered_residence"):
            profile_desc_parts.append(f"戶籍地: {profile['registered_residence']}")
        if profile.get("identity"):
            id_str = "、".join(profile["identity"]) if isinstance(profile["identity"], list) else profile["identity"]
            profile_desc_parts.append(f"身分: {id_str}")
        if profile.get("need"):
            profile_desc_parts.append(f"需求: {profile['need']}")
        if profile_desc_parts:
            profile_section = "【使用者已知條件】\n" + "\n".join(profile_desc_parts) + "\n\n"
            system_prompt = profile_section + system_prompt

    # 構建帶歷史的 messages
    llm_messages = [{"role": "system", "content": system_prompt}]

    recent_messages = messages[-6:] if len(messages) > 6 else messages
    for msg in recent_messages[:-1]:
        if isinstance(msg, HumanMessage):
            llm_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            llm_messages.append({"role": "assistant", "content": msg.content})

    user_prompt = PROMPTS[lang]["rag_user"].format(question=question, context_for_llm=context_for_llm)
    llm_messages.append({"role": "user", "content": user_prompt})

    response = await openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=llm_messages,
        temperature=0.0,
        stream=False,
    )
    answer = response.choices[0].message.content.strip()
    logger.info(f"[Generate] Answer length: {len(answer)} chars, profile_sufficient={profile_sufficient}")

    return {"messages": [AIMessage(content=answer)], "_usage": _usage_to_dict(response.usage)}


# ─────────────────────────────────────────
# Node 4: Small Talk（閒聊）
# ─────────────────────────────────────────
async def small_talk_node(state: AgentState) -> dict:
    """處理非獎學金相關的閒聊、問候等。"""
    messages = state["messages"]
    lang = state.get("lang", "zh")

    last_human = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    question_lang = _detect_language(last_human)
    base_prompt = PROMPTS[lang]["small_talk_system"]
    if question_lang == "en":
        base_prompt += "\n\n⚠️ CRITICAL: The user is writing in English. You MUST respond in English."
    else:
        base_prompt += "\n\n⚠️ 使用者使用中文提問，你必須使用繁體中文回答。"

    llm_messages = [{"role": "system", "content": base_prompt}]
    recent = messages[-4:] if len(messages) > 4 else messages
    for msg in recent[:-1]:
        if isinstance(msg, HumanMessage):
            llm_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            llm_messages.append({"role": "assistant", "content": msg.content})
    llm_messages.append({"role": "user", "content": last_human})

    response = await openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=llm_messages,
        temperature=0.7,
        max_completion_tokens=500,
    )
    answer = response.choices[0].message.content.strip()
    logger.info(f"[SmallTalk] Answer generated (length={len(answer)})")
    return {"messages": [AIMessage(content=answer)], "retrieved_docs": [], "_usage": _usage_to_dict(response.usage)}
