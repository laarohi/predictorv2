"""Promote an existing user to admin by email.

Usage (inside the backend container):
    python -m scripts.make_admin someone@example.com

Complements the ADMIN_EMAILS bootstrap (which grants admin on
creation/login): use this to promote an account that already exists.
"""

import asyncio
import sys

from sqlmodel import select

from app.database import async_session_maker
from app.models.user import User


async def _make_admin(email: str) -> int:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user found with email: {email}")
            return 1
        if user.is_admin:
            print(f"{email} is already an admin.")
            return 0
        user.is_admin = True
        session.add(user)
        await session.commit()
        print(f"{email} is now an admin.")
        return 0


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.make_admin <email>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_make_admin(sys.argv[1])))


if __name__ == "__main__":
    main()
