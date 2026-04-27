"""HTTP authentication middleware."""

from __future__ import annotations

from fastapi import Request
from starlette.responses import JSONResponse, Response

from src.auth.dependencies import get_auth_service
from src.auth.exceptions import AuthError
from src.auth.session import SESSION_COOKIE_NAME

PUBLIC_PATH_PREFIXES = (
    "/api/auth",
    "/api/assets/",
    "/static/avatars",
    "/docs",
    "/redoc",
)
PUBLIC_PATHS = {"/health", "/openapi.json"}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


async def auth_middleware(request: Request, call_next) -> Response:
    """Protect HTTP routes when auth is enabled."""
    auth_service = get_auth_service(request.app)
    if not auth_service.enabled or request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    try:
        user = auth_service.authenticate_credentials(
            authorization=request.headers.get("Authorization"),
            session_token=request.cookies.get(SESSION_COOKIE_NAME),
        )
    except AuthError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=401)

    request.state.user_id = user.username
    return await call_next(request)
