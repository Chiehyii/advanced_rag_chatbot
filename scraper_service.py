import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from logger import get_logger

logger = get_logger(__name__)

def _get_hash_if_url(url: str):
    if not url: return None, None
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        return hashlib.md5(text.encode('utf-8')).hexdigest(), datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.warning(f"[Scraper Service] Failed to get hash for {url}: {e}")
        return None, None
