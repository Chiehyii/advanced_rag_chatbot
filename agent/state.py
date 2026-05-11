# -*- coding: utf-8 -*-
"""
Agent State Definition
======================
定義 LangGraph Agent 的共用狀態，所有 Node 都讀寫這個 State。
"""
from __future__ import annotations
from typing import Annotated, Any, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class UserProfile(TypedDict, total=False):
    """
    使用者輪廓：跨輪次累積的條件資訊。
    所有欄位都是 optional（total=False），初始為空 dict，
    由 profile_extraction_node 逐步填入。
    """
    education_system: str          # 學制：大學部 / 碩士班 / 博士班 / 五專 / 五專(4至5年級) /二技
    identity: list[str]            # 身分：低收入戶 / 原住民 / 一般生 ...
    need: str                      # 需求：生活補助 / 海外交流 / 急難救助 ...
    specific_name: str             # 使用者指定的獎學金名稱
    registered_residence: str      # 戶籍地：臺北市 / 花蓮縣 / 不限 ...
    nationality: str               # 國籍：本國籍 / 外籍生 / 僑生 / 港澳生


class AgentState(TypedDict, total=False):
    """
    Agent 的主狀態結構。
    - messages: 對話歷史，使用 add_messages reducer 自動合併。
    - user_profile: 跨輪次累積的使用者條件。
    - retrieved_docs: 暫存本輪檢索到的文件（cleaned contexts）。
    - current_intent: 本輪路由判斷結果（scholarship / other）。
    - lang: 語言 (zh / en)。
    - title_filter: 前端傳入的獎學金標題篩選清單。
    - request_id / session_id / user_id: 日誌追蹤用。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_profile: UserProfile
    retrieved_docs: list[dict]
    current_intent: str
    lang: str
    title_filter: list[str] | None
    request_id: str | None
    session_id: str | None
    user_id: str | None
    _profile_sufficient: bool  # profile_extraction_node 設定，供 routing 判斷
    _usage: Any               # 各 node 的 OpenAI usage，由 stream_agent_pipeline 累加
