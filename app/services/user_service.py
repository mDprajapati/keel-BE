"""Admin user management (v3 §14). Roles gate admin actions only."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, LastAdminError, NotFoundError
from app.core.security import hash_password
from app.models.base import Role
from app.models.organization import Workspace
from app.models.user import OrganizationMember, User
from app.schemas.auth import UserOut


def _to_out(user: User, role: str) -> UserOut:
    return UserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=Role(role),
        last_active_at=user.last_active_at,
    )


async def list_users(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[UserOut]:
    rows = (
        await db.execute(
            select(User, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.workspace_id == workspace_id)
        )
    ).all()
    return [_to_out(user, member.role) for user, member in rows]


async def _members_in_workspace(db, workspace_id):
    return (
        (
            await db.execute(
                select(OrganizationMember).where(OrganizationMember.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )


async def invite(db: AsyncSession, *, workspace_id: uuid.UUID, email: str, role: Role) -> UserOut:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    email = email.lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        member = (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.user_id == existing.id,
                    OrganizationMember.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if member is not None:
            raise ConflictError("User is already a member of this workspace")
        user = existing
    else:
        user = User(
            email=email,
            full_name=email.split("@")[0],
            password_hash=hash_password(secrets.token_urlsafe(24)),  # unusable until accept
        )
        db.add(user)
        await db.flush()

    db.add(
        OrganizationMember(
            organization_id=workspace.organization_id,
            workspace_id=workspace_id,
            user_id=user.id,
            role=role.value,
            invited_email=email,
            invite_accepted=False,
        )
    )
    await db.commit()
    return _to_out(user, role.value)


async def change_role(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: Role
) -> UserOut:
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.workspace_id == workspace_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise NotFoundError("User not found in workspace")

    # Guard: don't demote the last admin.
    if member.role == Role.admin.value and role != Role.admin:
        admins = [
            m for m in await _members_in_workspace(db, workspace_id) if m.role == Role.admin.value
        ]
        if len(admins) <= 1:
            raise LastAdminError("You cannot demote the last Admin in the workspace.")

    member.role = role.value
    await db.commit()
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found in workspace")
    return _to_out(user, role.value)


async def remove_user(db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.workspace_id == workspace_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise NotFoundError("User not found in workspace")

    if member.role == Role.admin.value:
        admins = [
            m for m in await _members_in_workspace(db, workspace_id) if m.role == Role.admin.value
        ]
        if len(admins) <= 1:
            raise LastAdminError("You cannot remove the last Admin in the workspace.")

    await db.delete(member)  # removes membership, not the user account (v3 §14.3)
    await db.commit()
