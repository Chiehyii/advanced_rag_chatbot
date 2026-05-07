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
import asyncio
from openai import AsyncOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Optional

import config
from agent.state import AgentState, UserProfile
from prompts import PROMPTS
from scripts.query_analyzer import analyze_query
from db_repository import clean_retrieved_contexts
from rag_service import get_embedding, retrieve_context
from logger import get_logger

logger = get_logger(__name__)

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


# ─────────────────────────────────────────
# Pydantic model for structured extraction
# ─────────────────────────────────────────
class ExtractedProfile(BaseModel):
    """LLM 從對話中萃取出的使用者條件"""
    education_system: Optional[str] = Field(None, description="學制，例如 大學部 / 碩士班 / 博士班 / 五專 / 二技")
    nationality: Optional[str] = Field(None, description="國籍，例如 本國籍 / 外籍生 / 僑生 / 港澳生")
    registered_residence: Optional[str] = Field(None, description="戶籍地，例如 臺北市 / 花蓮縣 / 不限")
    identity: Optional[list[str]] = Field(None, description="身分，例如 ['低收入戶', '原住民']")
    need: Optional[str] = Field(None, description="需求，例如 生活補助 / 海外交流 / 急難救助")
    specific_name: Optional[str] = Field(None, description="使用者指定的獎學金名稱")
    is_sufficient: bool = Field(False, description="條件是否足夠（需要 nationality + education_system，或 specific_name）")


# ─────────────────────────────────────────
# Node 1: Intent Router（意圖路由）
# ─────────────────────────────────────────
async def intent_router_node(state: AgentState) -> dict:
    """
    判斷最新一則使用者訊息的意圖：scholarship 或 other。
    不再生成 Milvus 過濾條件（已移至 retrieve_node）。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    title_filter = state.get("title_filter")

    # 取出最新的 HumanMessage
    last_human = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    # 如果前端有帶 title_filter，直接走 scholarship
    if title_filter and len(title_filter) > 0:
        logger.info(f"[Router] Title filter detected: {title_filter} → scholarship")
        return {"current_intent": "scholarship"}

    # 純意圖分類（analyze_query 已簡化為只回傳 intent 字串）
    try:
        intent = await analyze_query(last_human, lang=lang)
        logger.info(f"[Router] Intent={intent}")
    except Exception as e:
        logger.warning(f"[Router] analyze_query failed ({type(e).__name__}), defaulting to scholarship.")
        intent = "scholarship"

    return {"current_intent": intent}


# ─────────────────────────────────────────
# Node 2: Profile Extraction（條件萃取）
# ─────────────────────────────────────────
async def profile_extraction_node(state: AgentState) -> dict:
    """
    從完整對話歷史中萃取 UserProfile。
    每次都從完整歷史重新萃取，避免遺漏前面輪次的條件。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    existing_profile = state.get("user_profile", {})

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
            logger.warning("[Profile] Extraction returned None, keeping existing profile.")
            return {"user_profile": existing_profile}

        # 合併到現有 profile（新值覆蓋舊值，但不清除舊的）
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

        logger.info(f"[Profile] Extracted profile: {new_profile}, is_sufficient={extracted.is_sufficient}")
        return {"user_profile": new_profile, "_profile_sufficient": extracted.is_sufficient}

    except Exception as e:
        logger.error(f"[Profile] Extraction failed: {e}", exc_info=True)
        return {"user_profile": existing_profile, "_profile_sufficient": False}


# ─────────────────────────────────────────
# Node 3: Clarification（反問釐清）
# ─────────────────────────────────────────
async def clarify_node(state: AgentState) -> dict:
    """
    當條件不足時，生成反問訊息，引導使用者提供更多條件。
    """
    lang = state.get("lang", "zh")
    profile = state.get("user_profile", {})
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)

    system_prompt = PROMPTS[lang]['clarify_system'].format(profile_json=profile_json)

    # 把最新的使用者訊息也傳入，讓回覆更自然
    last_human = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    response = await openai_client.chat.completions.create(
        model=config.OPENAI_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": last_human},
        ],
        temperature=0.7,
        max_completion_tokens=500,
    )
    clarify_text = response.choices[0].message.content.strip()
    logger.info(f"[Clarify] Generated clarification: {clarify_text[:80]}...")

    return {"messages": [AIMessage(content=clarify_text)], "retrieved_docs": []}


# ─────────────────────────────────────────
# Utility: Profile → Milvus Expression
# ─────────────────────────────────────────
def build_milvus_expr_from_profile(profile: dict, title_filter: list[str] | None = None) -> str:
    """
    根據跨輪次累積的 user_profile，動態生成精確的 Milvus 過濾表達式。

    過濾規則（精確匹配，無寬容邏輯）：
    - registered_residence: 使用者戶籍 OR "不限"
    - nationality: 精確匹配（必填欄位）
    - education_system: 精確匹配（必填欄位）
    - identity: 使用者身分 OR "一般生"
    - tags: 精確匹配（可選）
    """
    # 前端指定特定獎學金 → 直接精準匹配，跳過 profile-based 過濾
    if title_filter and len(title_filter) > 0:
        safe_titles = [t.replace('"', '\\"') for t in title_filter[:3]]
        title_exprs = ", ".join([f'"{t}.md"' for t in safe_titles])
        expr = f"source_file in [{title_exprs}]"
        logger.info(f"[Filter] Title filter override: {expr}")
        return expr

    parts = []

    # --- registered_residence: 使用者戶籍 OR "不限" ---
    residence = profile.get("registered_residence")
    if residence and residence != "不限":
        parts.append(
            f'(ARRAY_CONTAINS(registered_residence, "{residence}") or '
            f'ARRAY_CONTAINS(registered_residence, "不限"))'
        )

    # --- nationality: 精確匹配 ---
    nationality = profile.get("nationality")
    if nationality:
        parts.append(f'ARRAY_CONTAINS(nationality, "{nationality}")')

    # --- education_system: 精確匹配 ---
    edu = profile.get("education_system")
    if edu:
        parts.append(f'ARRAY_CONTAINS(education_system, "{edu}")')

    # --- identity: 使用者身分 OR "一般生" ---
    identities = profile.get("identity")
    if identities and isinstance(identities, list):
        # 過濾掉 "一般生"，因為我們會自動加入
        special_ids = [i for i in identities if i != "一般生"]
        if special_ids:
            # 有特殊身分：匹配特殊身分 OR 一般生
            all_ids = special_ids + ["一般生"]
            vals_str = ", ".join([f'"{v}"' for v in all_ids])
            parts.append(f'ARRAY_CONTAINS_ANY(identity, [{vals_str}])')
        else:
            # 只有一般生
            parts.append('ARRAY_CONTAINS(identity, "一般生")')

    # --- tags: 精確匹配（可選）---
    # tags 來自 need 的推斷，暫不自動生成，由語意搜尋處理

    if parts:
        expr = " AND ".join([f"({p})" for p in parts])
        logger.info(f"[Filter] Profile-based expr: {expr}")
        return expr

    logger.info("[Filter] No profile conditions → no filter applied.")
    return ""


# ─────────────────────────────────────────
# Node 4: Retrieve（Milvus 檢索）
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

    # 構造檢索用的問題：使用最後一則 HumanMessage + 條件強化
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

    # 構建最終搜尋問題
    if title_filter and len(title_filter) > 0:
        title_str = "、".join(title_filter[:3]) if lang == "zh" else ", ".join(title_filter[:3])
        prefix = f"關於「{title_str}」：" if lang == "zh" else f"Regarding '{title_str}': "
        search_question = prefix + last_human
    elif profile_parts:
        profile_str = "、".join(profile_parts)
        search_question = f"({profile_str}) {last_human}"
    else:
        search_question = last_human

    logger.info(f"[Retrieve] Search question: {search_question}")

    # 根據累積的 profile 生成 Milvus 過濾條件
    expr = build_milvus_expr_from_profile(profile, title_filter)

    # 翻譯（如果是英文）
    question_for_retrieval = search_question
    if lang == "en":
        try:
            from llm_service import _translate_to_zh
            question_for_retrieval = await _translate_to_zh(search_question)
        except Exception:
            pass

    # 取得 embedding + 檢索
    try:
        embedding = await get_embedding(search_question)
        raw_docs = await retrieve_context(search_question, question_for_retrieval, embedding, expr)
        cleaned = clean_retrieved_contexts(raw_docs)
        logger.info(f"[Retrieve] Found {len(cleaned)} documents after cleaning.")
        return {"retrieved_docs": cleaned}
    except Exception as e:
        logger.error(f"[Retrieve] Failed: {e}", exc_info=True)
        return {"retrieved_docs": []}


# ─────────────────────────────────────────
# Node 5: Generate RAG Answer（答案生成）
# ─────────────────────────────────────────
async def generate_node(state: AgentState) -> dict:
    """
    結合 user_profile + 檢索文件，生成最終 RAG 回答。
    重點改善：把對話歷史也帶入 LLM，讓回答有對話連貫感。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")
    cleaned_contexts = state.get("retrieved_docs", [])
    profile = state.get("user_profile", {})

    # 取得最後一則 HumanMessage 作為 question
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

    # --- 組裝 messages for LLM（帶入對話歷史 + user_profile）---
    system_prompt = PROMPTS[lang]["rag_system"]

    # 加入 profile context 讓 LLM 知道目前已知的使用者條件
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

    # 加入最近的對話歷史（最多 6 條），讓 LLM 有對話連貫感
    recent_messages = messages[-6:] if len(messages) > 6 else messages
    for msg in recent_messages[:-1]:  # 排除最後一條（我們會用 rag_user prompt）
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
        stream=False,  # 在 Graph Node 中先用 non-stream；串流由外層處理
    )
    answer = response.choices[0].message.content.strip()
    logger.info(f"[Generate] Answer length: {len(answer)} chars")

    return {"messages": [AIMessage(content=answer)]}


# ─────────────────────────────────────────
# Node 6: Small Talk（閒聊）
# ─────────────────────────────────────────
async def small_talk_node(state: AgentState) -> dict:
    """
    處理非獎學金相關的閒聊、問候等。
    帶入對話歷史讓回覆更自然。
    """
    messages = state["messages"]
    lang = state.get("lang", "zh")

    last_human = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    # 帶入最近 4 條歷史
    llm_messages = [{"role": "system", "content": PROMPTS[lang]["small_talk_system"]}]
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
    logger.info(f"[SmallTalk] Answer: {answer[:80]}...")
    return {"messages": [AIMessage(content=answer)], "retrieved_docs": []}
