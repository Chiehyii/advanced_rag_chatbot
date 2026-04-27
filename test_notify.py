# test_notify.py
import os
from dotenv import load_dotenv

load_dotenv()
from notifier import send_line_message

send_line_message("這是一條來自 AI RAG Chatbot 的測試通知！")
