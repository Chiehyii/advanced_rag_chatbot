# -*- coding: utf-8 -*-
"""
Agent Graph Assembly
====================
將 Nodes 和 Edges 組裝成 LangGraph 的 StateGraph，編譯為可執行的 CompiledGraph。

流程設計（每次使用者發送訊息 = 一次完整的圖執行）：

    ┌─────────────────────────────── 跨輪次迴圈（MemorySaver 保存 user_profile）─┐
    │                                                                            │
    │  START                                                                     │
    │    │                                                                       │
    │    ▼                                                                       │
    │  intent_router                                                             │
    │    │                                                                       │
    │    ├── "other" ──► small_talk ──► END                                      │
    │    │                                                                       │
    │    └── "scholarship" ──► profile_extraction                                │
    │                               │                                            │
    │                               ├── sufficient ──► retrieve ──► generate ──► END
    │                               │                                            │
    │                               └── insufficient ──► clarify ──► END         │
    │                                                      │                     │
    │                                                      ▼                     │
    │                                              (等待使用者回覆)               │
    │                                                      │                     │
    └──────────────────────────── 使用者回覆後重新觸發 ──────┘
"""
from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes import (
    intent_router_node,
    profile_extraction_node,
    clarify_node,
    retrieve_node,
    generate_node,
    small_talk_node,
)
from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────
# Routing functions (conditional edges)
# ─────────────────────────────────────────
def route_by_intent(state: AgentState) -> str:
    """根據 intent 決定走 scholarship 或 small_talk 分支"""
    intent = state.get("current_intent", "other")
    if intent == "scholarship":
        return "profile_extraction"
    return "small_talk"


def route_by_profile(state: AgentState) -> str:
    """
    根據 profile 萃取結果決定：
    - 條件充足 → 進入 retrieve
    - 條件不足 → 進入 clarify
    """
    sufficient = state.get("_profile_sufficient", False)
    if sufficient:
        return "retrieve"
    return "clarify"


# ─────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────
def build_graph(checkpointer=None):
    """
    組裝並編譯 Agent StateGraph。
    
    Args:
        checkpointer: LangGraph Checkpointer 實例。
                      傳入 MemorySaver() 可讓 Graph 跨輪次保持狀態。
                      傳入 None 則每次都是全新狀態（需由外部手動傳入歷史）。
    
    Returns:
        CompiledGraph 實例，支援 ainvoke / astream / astream_events。
    """
    builder = StateGraph(AgentState)

    # --- Add Nodes ---
    builder.add_node("intent_router", intent_router_node)
    builder.add_node("profile_extraction", profile_extraction_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_node("small_talk", small_talk_node)

    # --- Add Edges ---
    # START → intent_router
    builder.add_edge(START, "intent_router")

    # intent_router → (profile_extraction | small_talk)
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {"profile_extraction": "profile_extraction", "small_talk": "small_talk"},
    )

    # profile_extraction → (retrieve | clarify)
    builder.add_conditional_edges(
        "profile_extraction",
        route_by_profile,
        {"retrieve": "retrieve", "clarify": "clarify"},
    )

    # retrieve → generate
    builder.add_edge("retrieve", "generate")

    # Terminal nodes → END
    builder.add_edge("generate", END)
    builder.add_edge("clarify", END)
    builder.add_edge("small_talk", END)

    # --- Compile ---
    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("[Graph] Agent StateGraph compiled successfully.")
    return compiled


# ─────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────
# 使用 MemorySaver 作為跨輪次對話記憶（In-memory，重啟即失）
memory = MemorySaver()
graph = build_graph(checkpointer=memory)
