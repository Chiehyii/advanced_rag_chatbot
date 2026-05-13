import hashlib
import hmac

from fastapi.responses import JSONResponse

ANONYMOUS_USER_COOKIE_NAME = "anonymous_user"


def sign_session_id(session_id: str, secret_key: str) -> str:
    signature = hmac.new(
        secret_key.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{session_id}.{signature}"


def verify_signed_session(value: str | None, secret_key: str) -> str | None:
    if not value or "." not in value:
        return None
    session_id, signature = value.rsplit(".", 1)
    if len(session_id) != 32:
        return None
    expected = hmac.new(
        secret_key.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if hmac.compare_digest(signature, expected):
        return session_id
    return None


class RequestBodyLimitMiddleware:
    """Enforce a hard request body limit, including chunked requests."""

    def __init__(self, app, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        body_size = 0
        buffered_messages = []
        more_body = True

        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                buffered_messages.append(message)
                break

            body_size += len(message.get("body", b""))
            if body_size > self.max_body_size:
                response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
                await response(scope, receive, send)
                return

            buffered_messages.append(message)
            more_body = message.get("more_body", False)

        async def replay_receive():
            if buffered_messages:
                return buffered_messages.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)
