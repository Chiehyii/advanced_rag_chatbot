# 日誌
import logging
import sys 
import os

# 引入處理「依照時間切割檔案」的工具
from logging.handlers import TimedRotatingFileHandler

def get_logger(name: str):
    """
    取得一個設定好格式的 logger 實例
    """
    logger = logging.getLogger(name)

    # 確保不會重複加入 handler (避免重複輸出)
    if not logger.handlers:
        # 設定層級
        # 預設只印出 INFO 以上等級的訊息
        logger.setLevel(logging.INFO)
        # 設定專業的日誌格式: 時間 - 模組名稱 - 等級 - 訊息
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
        )

        # 1. 設定輸出到終端機 (Console)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. 設定輸出到檔案 (File), 每天自動切換新檔案, 存在logs資料夾
        if not os.path.exists("logs"):
            os.makedirs("logs")

        # 建立一個「每天」自動切換的檔案 handler
        # when='midnight' -> 每天午夜 00:00 自動切換到新檔案
        # interval=1 -> 間隔 1 天
        # backupCount=7 -> 保留最近 7 天的 log 檔案 (避免佔用太多空間)
        file_handler = TimedRotatingFileHandler(
            filename="logs/adv_rag_chatbot.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        
        # 設定檔案名稱加上日期後綴, exp: adv_rag_chatbot.2026-03-19
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(formatter)
        # 將 handler 加入 logger
        logger.addHandler(file_handler)

    return logger