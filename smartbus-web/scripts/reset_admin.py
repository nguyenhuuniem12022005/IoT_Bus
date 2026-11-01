"""Apply the configured admin credentials, including to an existing account."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from app.core.security import hash_password, verify_password

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        users = client[settings.mongodb_db].users
        await users.update_one({'username': settings.seed_admin_username}, {'$set': {
            'role': 'admin', 'password_hash': hash_password(settings.seed_admin_password)
        }}, upsert=True)
        user = await users.find_one({'username': settings.seed_admin_username})
        assert verify_password(settings.seed_admin_password, user['password_hash'])
        print('Admin credentials updated and verified.')
    finally:
        client.close()

if __name__ == '__main__':
    asyncio.run(main())
