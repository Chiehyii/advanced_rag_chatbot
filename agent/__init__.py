# -*- coding: utf-8 -*-
"""
LangGraph Agent Workflow Module
===============================
將原本線性 RAG pipeline 改為狀態機驅動的 Agent 工作流。
支援多輪條件收集（Profile Extraction）與反問釐清（Clarification）。
"""
from agent.graph import build_graph  # noqa: F401
