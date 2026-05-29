import logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logging.getLogger('pyrogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

import os
import time
import asyncio
try:
    import uvloop
    ul = True
except ImportError:
    ul = False
    pass

from pyrogram import types, Client, StopPropagation
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait, TokenInvalid
from aiohttp import web
from typing import Union, Optional, AsyncGenerator

from web import web_app
from info import URL, INDEX_CHANNELS, SUPPORT_GROUP, LOG_CHANNEL, API_ID, DATA_DATABASE_URL, API_HASH, BOT_TOKEN, PORT, BIN_CHANNEL, ADMINS, SECOND_FILES_DATABASE_URL, FILES_DATABASE_URL
from utils import temp, get_readable_time, check_premium
from database.users_chats_db import db
from database.ia_filterdb import setup_database
from plugins.clone_db import clone_db  # Imported database script for tracking clones

if ul:
    uvloop.install()

# Dictionary to hold running clone bot instances in memory
# Key: bot_token, Value: Pyrogram Client object
running_clones = {}

class MasterBot(Client):
    def __init__(self):
        super().__init__(
            name='Auto_Filter_Bot',
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"} # Loads all handlers globally
        )
        self.listeners = {}
        self.add_handler(MessageHandler(self._listener_handler), group=-1)

    async def _listener_handler(self, client: Client, message: types.Message):
        if not message.chat or not message.from_user:
            return
        
        listener_id = (message.chat.id, message.from_user.id)
        if listener_id in self.listeners:
            future = self.listeners[listener_id]
            if not future.done():
                future.set_result(message)
            raise StopPropagation

    async def listen(self, chat_id: int, user_id: int, timeout: int = 60) -> Optional[types.Message]:
        future = asyncio.get_event_loop().create_future()
        listener_id = (chat_id, user_id)
        
        if listener_id in self.listeners:
            old_future = self.listeners[listener_id]
            if not old_future.done():
                old_future.cancel()
                
        self.listeners[listener_id] = future
        
        try:
            message = await asyncio.wait_for(future, timeout)
            return message
        except asyncio.TimeoutError:
            return None
        finally:
            self.listeners.pop(listener_id, None)

    async def start(self, **kwargs):
        logger.info('Setting up your database, please wait a moment...')
        await setup_database()
        logger.info('Successfully setup the database!')
        
        # Start Master Bot Client
        await super().start()
        temp.START_TIME = time.time()
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats

        if os.path.exists('restart.txt'):
            with open("restart.txt") as file:
                chat_id, msg_id = map(int, file)
            try:
                await self.edit_message_text(chat_id=chat_id, message_id=msg_id, text='Restarted Successfully!')
            except:
                pass
            os.remove('restart.txt')

        temp.BOT = self
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        
        # Setup Web Server
        app_runner = web.AppRunner(web_app)
        await app_runner.setup()
        await web.TCPSite(app_runner, "0.0.0.0", PORT).start()

        # Background automation task
        asyncio.create_task(check_premium(self))
        
        try:
            await self.send_message(chat_id=LOG_CHANNEL, text=f"<b>{me.mention} Restarted! 🤖</b>")
        except:
            logger.error("Make sure bot admin in LOG_CHANNEL, exiting now")
            exit()
            
        logger.info(f"🔥 Master Bot [@{me.username}] and webapp [{URL}] started successfully ✓")

        # ---- Dynamic Clone Initialization Block ----
        all_clones = await clone_db.get_all_clones()
        logger.info(f"Found {len(all_clones)} subscriber clones in database. Initializing execution loops...")

        for clone in all_clones:
            token = clone['bot_token']
            asyncio.create_task(self.start_clone_instance(token))

    async def start_clone_instance(self, token: str) -> bool:
        """Spawns an independent runner client for a subscriber bot token."""
        if token in running_clones:
            return False
            
        # Create unique session string for each clone to avoid lock conflicts
        session_name = f"clone_{token.split(':')[0]}"
        
        # Instantiate clone client utilizing the SAME global plugin blueprints
        clone_app = Client(
            name=session_name,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=token,
            workers=50,
            plugins={"root": "plugins"} # Shares structural parsing hooks instantly
        )
        
        try:
            await clone_app.start()
            clone_me = await clone_app.get_me()
            running_clones[token] = clone_app
            logger.info(f"✅ Clone Launched Successfully: @{clone_me.username}")
            return True
        except TokenInvalid:
            logger.error(f"❌ Revoked/Invalid subscriber token found: {token}. Removing entry.")
            await clone_db.remove_clone(token)
            return False
        except Exception as e:
            logger.error(f"⚠️ Failed to spin up clone {token}: {str(e)}")
            return False

    async def stop_clone_instance(self, token: str) -> bool:
        """Gracefully removes a clone out of server memory execution."""
        if token in running_clones:
            try:
                await running_clones[token].stop()
                del running_clones[token]
                logger.info(f"🛑 Clone stopped and removed from memory loop: {token.split(':')[0]}")
                return True
            except Exception as e:
                logger.error(f"Error stopping clone loop: {e}")
        return False

    async def stop(self, **kwargs):
        # Gracefully shut down all running clones first
        logger.info("Stopping all active subscriber clones...")
        for token in list(running_clones.keys()):
            await self.stop_clone_instance(token)
            
        await super().stop()
        logger.info("Bot Stopped! Bye...")

    async def iter_messages(self: Client, chat_id: Union[int, str], limit: int, offset: int = 0) -> Optional[AsyncGenerator[types.Message, None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(chat_id, list(range(current, current+new_diff+1)))
            for message in messages:
                yield message
                current += 1

if __name__ == "__main__":
    master_engine = MasterBot()
    master_engine.run()
