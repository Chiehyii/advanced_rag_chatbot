import hashlib
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from logger import get_logger
from utils import FetchSSLError, UnsafeUrlError, safe_fetch_text

logger = get_logger(__name__)

def _get_hash_if_url(url: str):
    if not url or not url.strip():
        return None, None
    try:
        content = safe_fetch_text(url.strip(), timeout=10)
        soup = BeautifulSoup(content, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        return hashlib.md5(text.encode('utf-8')).hexdigest(), datetime.now(timezone.utc).isoformat()
    except UnsafeUrlError as e:
        logger.warning(f"[Scraper Service] Unsafe URL blocked for hashing: {url} ({e})")
        return None, None
    except FetchSSLError as e:
        logger.warning(f"[Scraper Service] SSL verification failed for hashing: {url} ({e})")
        return None, None
    except ValueError as e:
        logger.warning(f"[Scraper Service] Fetch rejected for hashing: {url} ({e})")
        return None, None
    except Exception as e:
        logger.warning(f"[Scraper Service] Failed to get hash for {url}: {e}")
        return None, None
