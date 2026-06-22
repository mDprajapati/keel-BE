"""Seed a demo admin + workspace for the §21 dress rehearsal.

Usage: python -m scripts.seed_admin
Idempotent: does nothing if the demo admin already exists.
"""

from __future__ import annotations

import asyncio

from app.database import get_session_factory
from app.models.user import User
from app.services import auth_service
from sqlalchemy import select

DEMO_EMAIL = "admin@keel.demo"
DEMO_PASSWORD = "DemoPassw0rd!23"  # noqa: S105 — local demo seed only
DEMO_ORG = "Acme Corporation"


async def main() -> None:
    factory = get_session_factory()
    async with factory() as db:
        existing = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Demo admin already exists: {DEMO_EMAIL}")
            return
        await auth_service.register(
            db,
            full_name="Demo Admin",
            email=DEMO_EMAIL,
            organization_name=DEMO_ORG,
            password=DEMO_PASSWORD,
        )
        await db.commit()
    print(f"Seeded admin -> email: {DEMO_EMAIL}  password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
