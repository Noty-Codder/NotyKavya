from pyrogram import filters

from KavyaMusic import app
from KavyaMusic.misc import SUDOERS
from KavyaMusic.utils.cleaner import run_cleanup, _mb
from roohifont import fancy, quote


@app.on_message(filters.command(["clean", "cleancache"]) & SUDOERS)
async def clean_now(client, message):
    """Run the auto cleaner right now (also posts the report in the logger group)."""
    msg = await message.reply_text(quote(f"<b>🧹 {fancy('Cleaning...')}</b>"))
    files, size = await run_cleanup(notify=True)
    await msg.edit_text(quote(f"<b>✅ {fancy('Cleaned')} : {files} {fancy('files')} · {_mb(size)}</b>"))
