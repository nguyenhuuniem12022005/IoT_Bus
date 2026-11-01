import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.security import seed_users
from app.database import create_indexes


async def main() -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
    try:
        db = client[settings.mongodb_db]
        await create_indexes(db, settings)
        await seed_users(db, settings)
        logging.info("Đã tạo tài khoản còn thiếu; giữ nguyên tài khoản hiện có")
    finally:
        client.close()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
