"""Auth service — atomic signup, login + lockout, refresh rotation (v3 §6)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    sha256_hex,
    verify_password,
)
from app.models.base import Role
from app.models.organization import Organization, Workspace
from app.models.user import OrganizationMember, RefreshToken, User
from app.schemas.auth import AuthTokenResponse, UserOut, WorkspaceOut


@dataclass
class AuthResult:
    response: AuthTokenResponse
    refresh_token: str  # raw; the router sets it as an HttpOnly cookie


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _now() -> datetime:
    return datetime.now(UTC)


def _build_response(
    access: str, user: User, workspace: Workspace, role: str, org_name: str
) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=access,
        user=UserOut(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=Role(role),
            last_active_at=user.last_active_at,
        ),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name, organization_name=org_name),
    )


async def _issue_tokens(
    db: AsyncSession, user: User, workspace: Workspace, role: str
) -> tuple[str, str]:
    access = create_access_token(user_id=str(user.id), workspace_id=str(workspace.id), role=role)
    raw, token_hash, expires_at = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id, workspace_id=workspace.id, token_hash=token_hash, expires_at=expires_at
        )
    )
    return access, raw


async def register(
    db: AsyncSession, *, full_name: str, email: str, organization_name: str, password: str
) -> AuthResult:
    existing = (
        await db.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("An account with this email already exists", error_code="EMAIL_TAKEN")

    org = Organization(name=organization_name, slug=_slugify(organization_name))
    db.add(org)
    await db.flush()
    workspace = Workspace(organization_id=org.id, name=organization_name)
    db.add(workspace)
    await db.flush()
    user = User(
        email=email.lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        last_active_at=_now(),
    )
    db.add(user)
    await db.flush()
    db.add(
        OrganizationMember(
            organization_id=org.id,
            workspace_id=workspace.id,
            user_id=user.id,
            role=Role.admin.value,
            invite_accepted=True,
        )
    )

    access, refresh_raw = await _issue_tokens(db, user, workspace, Role.admin.value)
    return AuthResult(
        _build_response(access, user, workspace, Role.admin.value, org.name), refresh_raw
    )


async def _membership(db: AsyncSession, user_id: uuid.UUID) -> OrganizationMember:
    member = (
        (await db.execute(select(OrganizationMember).where(OrganizationMember.user_id == user_id)))
        .scalars()
        .first()
    )
    if member is None:
        raise UnauthorizedError("No workspace membership")
    return member


async def _resolve_workspace_org(
    db: AsyncSession, member: OrganizationMember
) -> tuple[Workspace, Organization]:
    workspace = await db.get(Workspace, member.workspace_id)
    if workspace is None:
        raise UnauthorizedError("Workspace not found")
    org = await db.get(Organization, workspace.organization_id)
    if org is None:
        raise UnauthorizedError("Organization not found")
    return workspace, org


async def login(db: AsyncSession, *, email: str, password: str) -> AuthResult:
    user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("Invalid email or password")
    if user.lockout_until and user.lockout_until > _now():
        raise UnauthorizedError(
            "Account temporarily locked. Try again later.", error_code="ACCOUNT_LOCKED"
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_attempts:
            user.lockout_until = _now() + timedelta(minutes=settings.lockout_min)
            user.failed_login_count = 0
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is inactive")

    user.failed_login_count = 0
    user.lockout_until = None
    user.last_active_at = _now()

    member = await _membership(db, user.id)
    workspace, org = await _resolve_workspace_org(db, member)
    access, refresh_raw = await _issue_tokens(db, user, workspace, member.role)
    return AuthResult(_build_response(access, user, workspace, member.role, org.name), refresh_raw)


async def refresh(db: AsyncSession, *, raw_token: str) -> AuthResult:
    token = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw_token))
        )
    ).scalar_one_or_none()
    if token is None or token.revoked_at is not None or token.expires_at < _now():
        raise UnauthorizedError("Invalid or expired session", error_code="UNAUTHENTICATED")

    token.revoked_at = _now()  # rotate
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    member = await _membership(db, user.id)
    workspace, org = await _resolve_workspace_org(db, member)
    access, refresh_raw = await _issue_tokens(db, user, workspace, member.role)
    return AuthResult(_build_response(access, user, workspace, member.role, org.name), refresh_raw)


async def logout(db: AsyncSession, *, raw_token: str | None) -> None:
    if not raw_token:
        return
    token = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw_token))
        )
    ).scalar_one_or_none()
    if token and token.revoked_at is None:
        token.revoked_at = _now()


async def get_session(db: AsyncSession, *, user_id: uuid.UUID) -> tuple[UserOut, WorkspaceOut]:
    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("User not found")
    member = await _membership(db, user.id)
    workspace, org = await _resolve_workspace_org(db, member)
    return (
        UserOut(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=Role(member.role),
            last_active_at=user.last_active_at,
        ),
        WorkspaceOut(id=workspace.id, name=workspace.name, organization_name=org.name),
    )
