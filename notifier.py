import config
from logger import get_logger
import requests
import json

logger = get_logger(__name__)

def send_line_message(message: str):
    """
    Sends a push message to the specified LINE user using the LINE Messaging API.
    """
    token = config.LINE_CHANNEL_ACCESS_TOKEN
    user_id = config.LINE_USER_ID
    
    if not token or not user_id:
        logger.warning("[Notifier] LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID is not configured. Skipping notification.")
        return False
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        response.raise_for_status()
        logger.info("[Notifier] Successfully sent LINE notification.")
        return True
    except Exception as e:
        logger.error(f"[Notifier] Failed to send LINE notification: {e}\nResponse: {getattr(e.response, 'text', '')}")
        return False
