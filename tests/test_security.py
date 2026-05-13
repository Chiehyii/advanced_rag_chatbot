import asyncio
import json

from security import RequestBodyLimitMiddleware, sign_session_id, verify_signed_session


def test_signed_session_round_trip_and_tamper_rejection():
    session_id = "a" * 32
    secret = "test-secret"

    signed = sign_session_id(session_id, secret)

    assert verify_signed_session(signed, secret) == session_id
    assert verify_signed_session(signed.replace("a", "b", 1), secret) is None
    assert verify_signed_session(signed, "other-secret") is None
    assert verify_signed_session("not-signed", secret) is None


def test_request_body_limit_allows_small_chunked_body():
    received_body = bytearray()
    sent_messages = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            received_body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(app, max_body_size=10)
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware({"type": "http"}, receive, send))

    assert bytes(received_body) == b"abcdef"
    assert sent_messages[0]["status"] == 200


def test_request_body_limit_rejects_large_chunked_body():
    app_called = False
    sent_messages = []

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

    middleware = RequestBodyLimitMiddleware(app, max_body_size=5)
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware({"type": "http"}, receive, send))

    assert app_called is False
    assert sent_messages[0]["status"] == 413
    body = json.loads(sent_messages[1]["body"])
    assert body["detail"] == "Request body too large"
