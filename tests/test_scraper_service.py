from scraper_service import _get_hash_if_url


def test_get_hash_if_url_uses_safe_fetch(monkeypatch):
    calls = []

    def fake_fetch(url, timeout=10):
        calls.append((url, timeout))
        return "<html><body>Hello scholarship</body></html>"

    monkeypatch.setattr("scraper_service.safe_fetch_text", fake_fetch)

    content_hash, checked_at = _get_hash_if_url(" https://example.com/page ")

    assert calls == [("https://example.com/page", 10)]
    assert content_hash == "2d8dc8b695a13e76a09f98cb13e4f6a7"
    assert checked_at is not None


def test_get_hash_if_url_rejects_unsafe_url():
    content_hash, checked_at = _get_hash_if_url("http://127.0.0.1")

    assert content_hash is None
    assert checked_at is None
