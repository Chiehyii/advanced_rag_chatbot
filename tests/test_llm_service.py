import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_service import _trim_history_to_budget

def test_trim_history_below_budget():
    """當前對話歷史沒有超過 token budget 時，應全數保留且順序不變"""
    history = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"}
    ]
    
    # 故意給一個極寬鬆的預算 (1000 tokens)
    trimmed_history = _trim_history_to_budget(history, budget=1000)
    
    assert len(trimmed_history) == 3
    # 確保順序沒被前後翻轉
    assert trimmed_history[0]["content"] == "Hello!"
    assert trimmed_history[2]["content"] == "How are you?"

def test_trim_history_exceeds_budget():
    """當對話歷史超過 token budget 時，優先丟棄最舊的訊息"""
    history = [
        {"role": "user", "content": "This is a very old message. "*10},
        {"role": "assistant", "content": "Got it, old message."},
        {"role": "user", "content": "This is the newest message."},
    ]
    
    # 故意給一個極苛刻的預算 (預期只能容納最後一句話)
    # 實際上 "user: This is the newest message." 大約 10 tokens
    trimmed_history = _trim_history_to_budget(history, budget=15)
    
    assert len(trimmed_history) == 1
    assert trimmed_history[0]["content"] == "This is the newest message."
    
def test_trim_history_edge_case():
    """即使是最新的第一句話自己就超過條件，基於防呆應該回傳空陣列"""
    history = [
        {"role": "user", "content": "Extremely long text... "*50}
    ]
    
    # 預算只有 5 個 token，此句話絕對裝不下
    trimmed_history = _trim_history_to_budget(history, budget=5)
    assert len(trimmed_history) == 0
