"""Auth endpoints (v3 §6). Access token in body; refresh token in HttpOnly cookie."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import Principal, get_current_user, get_db
from app.core.errors import UnauthorizedError
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest, SessionInfo
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "keel_refresh"
_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        httponly=True,
        secure=settings.app_env != "local",
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 86400,
        path=_COOKIE_PATH,
    )


@router.post("/register", response_model=AuthTokenResponse)
async def register(
    payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    result = await auth_service.register(
        db,
        full_name=payload.full_name,
        email=payload.email,
        organization_name=payload.organization_name,
        password=payload.password,
    )
    _set_refresh_cookie(response, result.refresh_token)
    return result.response


@router.post("/login", response_model=AuthTokenResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await auth_service.login(db, email=payload.email, password=payload.password)
    _set_refresh_cookie(response, result.refresh_token)
    return result.response


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise UnauthorizedError("No active session", error_code="UNAUTHENTICATED")
    result = await auth_service.refresh(db, raw_token=raw)
    _set_refresh_cookie(response, result.refresh_token)
    return result.response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await auth_service.logout(db, raw_token=request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path=_COOKIE_PATH)


@router.get("/me", response_model=SessionInfo)
async def me(principal: Principal = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user, workspace = await auth_service.get_session(db, user_id=principal.require_user())
    return SessionInfo(user=user, workspace=workspace)
