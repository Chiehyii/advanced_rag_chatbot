# -*- coding: utf-8 -*-
"""
Agent Graph Assembly
====================
將 Nodes 和 Edges 組裝成 LangGraph 的 StateGraph，編譯為可執行的 CompiledGraph。

流程設計（每次使用者發送訊息 = 一次完整的圖執行）：

    ┌─────────────────────── 跨輪次迴圈（MemorySaver 保存 user_profile）─┐
    │                                                                    │
    │  START                                                             │
    │    │                                                               │
    │    ▼                                                               │
    │  analyze_and_extract（意圖+條件萃取合一）                           │
    │    │                                                               │
    │    ├── "small_talk" ──► small_talk ──► END                         │
    │    │                                                               │
    │    └── "scholarship" ──► retrieve ──► generate ──► END             │
    │                                                                    │
    │  generate 會根據 _profile_sufficient 旗標自動調整回答深度：         │
    │    - True → 完整表格 + 詳細資訊                                     │
    │    - False → 預覽摘要 + 溫柔反問                                    │
    │                                                                    │
    └────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes import (
    analyze_and_extract_node,
    retrieve_node,
    generate_node,
    small_talk_node,
)
from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────
# Routing function (conditional edge)
# ─────────────────────────────────────────
def route_by_intent(state: AgentState) -> str:
    """根據 intent 決定走 scholarship 或 small_talk 分支"""
    intent = state.get("current_intent", "scholarship")
    if intent == "small_talk":
        return "small_talk"
    return "retrieve"


# ─────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────
def build_graph(checkpointer=None):
    """
    組裝並編譯 Agent StateGraph。
    
    Args:
        checkpointer: LangGraph Checkpointer 實例。
                      傳入 MemorySaver() 可讓 Graph 跨輪次保持狀態。
                      傳入 None 則每次都是全新狀態。
    
    Returns:
        CompiledGraph 實例，支援 ainvoke / astream / astream_events。
    """
    builder = StateGraph(AgentState)

    # --- Add Nodes ---
    builder.add_node("analyze_and_extract", analyze_and_extract_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_node("small_talk", small_talk_node)

    # --- Add Edges ---
    builder.add_edge(START, "analyze_and_extract")

    builder.add_conditional_edges(
        "analyze_and_extract",
        route_by_intent,
        {"retrieve": "retrieve", "small_talk": "small_talk"},
    )

    builder.add_edge("retrieve", "generate")

    # Terminal nodes → END
    builder.add_edge("generate", END)
    builder.add_edge("small_talk", END)

    # --- Compile ---
    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("[Graph] Agent StateGraph compiled successfully.")
    return compiled


# ─────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────
memory = MemorySaver()
graph = build_graph(checkpointer=memory)
