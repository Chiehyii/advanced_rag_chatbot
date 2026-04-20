import pytest
import sys
import os

# 將專案根目錄加入 PATH，以便匯入 utils.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import is_safe_url

def test_safe_urls():
    """測試正常外部允許的 URL"""
    assert is_safe_url("https://www.google.com") == True
    assert is_safe_url("http://example.com/some/path") == True

def test_unsafe_urls():
    """測試各種被 SSRF 拒絕的 URL"""
    # 錯誤的 Schema
    assert is_safe_url("ftp://example.com") == False
    assert is_safe_url("file:///etc/passwd") == False
    
    # 內部環回位址 (Loopback)
    assert is_safe_url("http://127.0.0.1") == False
    assert is_safe_url("https://localhost") == False
    
    # 內部私人網路 (Private IP)
    assert is_safe_url("http://192.168.1.100") == False
    assert is_safe_url("http://10.0.0.5") == False
    
    # AWS Metadata IP
    assert is_safe_url("http://169.254.169.254") == False

def test_invalid_urls():
    """測試畸形或無法解析的 URL"""
    assert is_safe_url("not_a_url") == False
    assert is_safe_url("") == False
