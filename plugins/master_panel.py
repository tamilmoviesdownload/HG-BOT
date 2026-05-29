from pyrogram import Client, filters
from pyrogram.types import Message
from info import ADMINS  # Assuming your admin IDs array is imported here
from plugins.clone_db import clone_db
# Import instance tracking from bot.py context 
from bot import master_engine, running_clones

@Client.on_message(filters.command("create_clone") & filters.user(ADMINS))
async def create_clone_handler(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text("**Format:** `/create_clone [bot_token] [owner_telegram_id]`")
        
    token = message.command[1]
    owner_id = message.command[2]
    
    progress = await message.reply_text("⚡ *Processing request: Validating session handshake...*")
    
    # Add token parameters to universal db
    await clone_db.add_clone(bot_token=token, owner_id=owner_id)
    
    # Programmatically instruct running engine to boot client without restarting main bot
    success = await master_engine.start_clone_instance(token)
    
    if success:
        await progress.edit(f"🚀 **Clone successfully integrated!**\n\nBot is now pulling indexes from the master database with 1M+ files live.")
    else:
        await progress.edit("❌ **Handshake rejected.** Ensure token is valid and not already running.")

@Client.on_message(filters.command("delete_clone") & filters.user(ADMINS))
async def delete_clone_handler(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("**Format:** `/delete_clone [bot_token]`")
        
    token = message.command[1]
    
    # Disconnect loop from instance memory
    await master_engine.stop_clone_instance(token)
    # Wipe credentials record from db
    await clone_db.remove_clone(token)
    
    await message.reply_text("🛑 **Subscriber bot terminated.** Runtime loops halted and memory buffers flushed.")
