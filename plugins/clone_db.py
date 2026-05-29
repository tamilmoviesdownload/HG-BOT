import time
from motor.motor_asyncio import AsyncIOMotorClient
from info import DATABASE_URL # Uses your master database URL

class CloneDatabase:
    def __init__(self):
        self.client = AsyncIOMotorClient(DATABASE_URL)
        self.db = self.client['CloneEngine']
        self.clones = self.db['active_clones']

    async def add_clone(self, bot_token, owner_id, shortener_url=None, shortener_api=None):
        """Registers a new subscriber clone bot into the master database."""
        clone_data = {
            "bot_token": bot_token,
            "owner_id": int(owner_id),
            "created_at": time.time(),
            "shortener_url": shortener_url,
            "shortener_api": shortener_api,
            "custom_start_text": None,
            "custom_title": None,
            "logs_channel": None,
            "clicks": 0,
            "total_users": []
        }
        await self.clones.update_one({"bot_token": bot_token}, {"$set": clone_data}, upsert=True)

    async def get_all_clones(self):
        """Retrieves all active clone tokens to spin up during startup."""
        cursor = self.clones.find({})
        return await cursor.to_list(length=None)

    async def get_clone_config(self, bot_token):
        """Fetches the configuration mapping for an active clone."""
        return await self.clones.find_one({"bot_token": bot_token})

    async def update_clone_setting(self, bot_token, key, value):
        """Updates per-clone settings dynamically (e.g., shortener, branding text)."""
        await self.clones.update_one({"bot_token": bot_token}, {"$set": {key: value}})

    async def remove_clone(self, bot_token):
        """Deletes a clone from the database when subscription is terminated."""
        await self.clones.delete_one({"bot_token": bot_token})

    async def increment_clicks(self, bot_token):
        """Tracks separate analytics for the clone."""
        await self.clones.update_one({"bot_token": bot_token}, {"$inc": {"clicks": 1}})

clone_db = CloneDatabase()
