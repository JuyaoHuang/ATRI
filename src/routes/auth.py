"""Authentication API routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from src.auth.dependencies import DEFAULT_USER_ID, get_auth_service
from src.auth.exceptions import AuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthStatusResponse(BaseModel):
    enabled: bool


class AuthLoginResponse(BaseModel):
    enabled: bool
    authorization_url: str | None = None


class AuthUserResponse(BaseModel):
    username: str
    avatar_url: str | None = None
    name: str | None = None
    auth_enabled: bool


class AuthLogoutResponse(BaseModel):
    success: bool


def _redirect_with_params(base_url: str, params: dict[str, str]) -> RedirectResponse:
    separator = "&" if "?" in base_url else "?"
    return RedirectResponse(f"{base_url}{separator}{urlencode(params)}")


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(request: Request) -> AuthStatusResponse:
    auth_service = get_auth_service(request.app)
    return AuthStatusResponse(enabled=auth_service.enabled)


@router.get("/login", response_model=AuthLoginResponse)
async def get_login_url(
    request: Request,
    state: str | None = Query(None),
) -> AuthLoginResponse:
    auth_service = get_auth_service(request.app)
    if not auth_service.enabled:
        return AuthLoginResponse(enabled=False, authorization_url=None)
    if auth_service.github_oauth is None:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")
    return AuthLoginResponse(
        enabled=True,
        authorization_url=auth_service.github_oauth.get_authorization_url(state=state),
    )


@router.get("/callback")
async def github_callback(
    request: Request,
    code: str | None = Query(None),
    error: str | None = Query(None),
) -> RedirectResponse:
    auth_service = get_auth_service(request.app)
    if not auth_service.enabled:
        return _redirect_with_params(auth_service.frontend_callback_url, {"auth": "disabled"})
    if error:
        return _redirect_with_params(auth_service.frontend_callback_url, {"error": error})
    if not code:
        return _redirect_with_params(auth_service.frontend_callback_url, {"error": "missing_code"})
    if auth_service.github_oauth is None:
        return _redirect_with_params(auth_service.frontend_callback_url, {"error": "oauth_config"})

    try:
        access_token = await auth_service.github_oauth.exchange_code_for_token(code)
        github_user = await auth_service.github_oauth.get_user_info(access_token)
        auth_service.require_allowed_user(github_user)
        token = auth_service.create_token_for_github_user(github_user)
    except AuthError as exc:
        return _redirect_with_params(
            auth_service.frontend_callback_url,
            {"error": "unauthorized", "detail": str(exc)},
        )
    except Exception:
        return _redirect_with_params(
            auth_service.frontend_callback_url,
            {"error": "github_oauth_failed"},
        )

    params = {
        "token": token,
        "username": github_user.username,
    }
    if github_user.avatar_url:
        params["avatar_url"] = github_user.avatar_url
    return _redirect_with_params(auth_service.frontend_callback_url, params)


@router.get("/me", response_model=AuthUserResponse)
async def get_current_user(request: Request) -> AuthUserResponse:
    auth_service = get_auth_service(request.app)
    if not auth_service.enabled:
        return AuthUserResponse(username=DEFAULT_USER_ID, auth_enabled=False)
    try:
        user = auth_service.authenticate_bearer_token(request.headers.get("Authorization"))
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return AuthUserResponse(
        username=user.username,
        avatar_url=user.avatar_url,
        name=user.name,
        auth_enabled=True,
    )


@router.post("/logout", response_model=AuthLogoutResponse)
async def logout() -> AuthLogoutResponse:
    return AuthLogoutResponse(success=True)

