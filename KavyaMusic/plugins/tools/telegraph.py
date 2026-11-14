"""/tgm  - reply to a photo / video / gif / sticker / file -> public link
   /tgt  - reply to text (or /tgt <text>) -> telegra.ph page

Telegraph shut its anonymous *image* upload, so /tgm uploads to free file hosts and
tries them one after the other (catbox -> envs.sh -> 0x0.st) until one answers.
Everything is deleted from the server right after the upload (Heroku-safe).
"""

import asyncio
import json
import os
import time

import aiohttp
from pyrogram import filters
from pyrogram.types import Message

from KavyaMusic import app
from KavyaMusic.utils.roohi import btn, rows_to_kb
from roohifont import fancy, quote
from config import BANNED_USERS

MAX_SIZE = 20 * 1024 * 1024          # 20 MB
COOLDOWN = 8                         # seconds per user
UA = {"User-Agent": "KavyaMusicBot/1.0 (+telegram)"}
_last_use = {}
_tg_token = {"value": None}


# ------------------------------------------------------------------ uploaders
async def _post_file(session, url, field, path, extra=None, headers=None):
    data = aiohttp.FormData()
    for k, v in (extra or {}).items():
        data.add_field(k, v)
    with open(path, "rb") as fh:
        data.add_field(field, fh, filename=os.path.basename(path))
        async with session.post(url, data=data, headers=headers or UA) as resp:
            text = (await resp.text()).strip()
            return resp.status, text


async def upload_file(path):
    """Returns (link, host) or (None, None)."""
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        hosts = (
            ("catbox", "https://catbox.moe/user/api.php", "fileToUpload", {"reqtype": "fileupload"}),
            ("envs.sh", "https://envs.sh", "file", None),
            ("0x0.st", "https://0x0.st", "file", None),
        )
        for name, url, field, extra in hosts:
            try:
                status, text = await _post_file(session, url, field, path, extra)
                if status == 200 and text.startswith("http"):
                    return text.split()[0], name
            except Exception:
                continue
    return None, None


async def _telegraph_page(title, text):
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if not _tg_token["value"]:
            async with session.get("https://api.telegra.ph/createAccount",
                                   params={"short_name": "KavyaMusic", "author_name": "KavyaMusic"}) as r:
                data = await r.json()
            if not data.get("ok"):
                raise RuntimeError(data)
            _tg_token["value"] = data["result"]["access_token"]
        content = [{"tag": "p", "children": [line]} for line in text.split("\n") if line.strip()] or \
                  [{"tag": "p", "children": ["-"]}]
        async with session.post("https://api.telegra.ph/createPage", data={
            "access_token": _tg_token["value"],
            "title": title[:200] or "KavyaMusic",
            "author_name": "KavyaMusic",
            "content": json.dumps(content),
        }) as r:
            data = await r.json()
        if not data.get("ok"):
            _tg_token["value"] = None
            raise RuntimeError(data)
        return data["result"]["url"]


# ------------------------------------------------------------------ helpers
def _media_info(msg: Message):
    """(media object, extension) for the first uploadable media in msg."""
    if msg.photo:
        return msg.photo, ".jpg"
    if msg.animation:
        return msg.animation, ".mp4"
    if msg.video:
        return msg.video, ".mp4"
    if msg.sticker:
        return msg.sticker, ".tgs" if msg.sticker.is_animated else (".webm" if msg.sticker.is_video else ".webp")
    if msg.audio:
        return msg.audio, os.path.splitext(msg.audio.file_name or "")[1] or ".mp3"
    if msg.voice:
        return msg.voice, ".ogg"
    if msg.video_note:
        return msg.video_note, ".mp4"
    if msg.document:
        return msg.document, os.path.splitext(msg.document.file_name or "")[1] or ".bin"
    return None, None


def _cooldown(user_id):
    now = time.time()
    if now - _last_use.get(user_id, 0) < COOLDOWN:
        return True
    _last_use[user_id] = now
    if len(_last_use) > 2000:
        _last_use.clear()
    return False


# ------------------------------------------------------------------ /tgm
@app.on_message(filters.command(["tgm", "telegraph"]) & ~BANNED_USERS)
async def tgm_upload(client, message: Message):
    if message.from_user and _cooldown(message.from_user.id):
        return await message.reply_text(fancy("Slow down, try again in a few seconds."))

    target = message.reply_to_message or message
    media, ext = _media_info(target)
    if not media:
        return await message.reply_text(quote(
            f"<b>🖼 {fancy('Reply to a photo / video / gif / file with')} <code>/tgm</code></b>"))
    if (getattr(media, "file_size", 0) or 0) > MAX_SIZE:
        return await message.reply_text(quote(f"<b>❌ {fancy('File is too big (max 20 MB).')}</b>"))

    status = await message.reply_text(quote(f"<b>⬇️ {fancy('Downloading...')}</b>"))
    os.makedirs("cache", exist_ok=True)
    stamp = f"{message.chat.id}_{message.id}_{int(time.time())}".replace("-", "m")
    path = None
    try:
        path = await client.download_media(target, file_name=f"cache/tgm_{stamp}{ext}")
        if not path or not os.path.exists(path):
            raise RuntimeError("download failed")
        await status.edit_text(quote(f"<b>⬆️ {fancy('Uploading...')}</b>"))
        link, host = await upload_file(path)
    except Exception:
        link = host = None
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    if not link:
        return await status.edit_text(quote(
            f"<b>❌ {fancy('Upload failed on every host. Please try again later.')}</b>"))

    await status.edit_text(
        quote(f"<b>✅ {fancy('Uploaded')} ({host})</b>\n\n<code>{link}</code>"),
        disable_web_page_preview=True,
        reply_markup=rows_to_kb([[btn("Open link", url=link)]]),
    )


# ------------------------------------------------------------------ /tgt
@app.on_message(filters.command(["tgt"]) & ~BANNED_USERS)
async def tgt_page(client, message: Message):
    if message.from_user and _cooldown(message.from_user.id):
        return await message.reply_text(fancy("Slow down, try again in a few seconds."))

    reply = message.reply_to_message
    text = (reply.text or reply.caption) if reply else None
    if not text and len(message.command) > 1:
        text = message.text.split(None, 1)[1]
    if not text:
        return await message.reply_text(quote(
            f"<b>📝 {fancy('Reply to a text with')} <code>/tgt</code> {fancy('or use')} <code>/tgt your text</code></b>"))

    title = text.strip().split("\n")[0][:60] or "KavyaMusic"
    try:
        link = await _telegraph_page(title, text)
    except Exception:
        return await message.reply_text(quote(f"<b>❌ {fancy('Could not create the page. Try again later.')}</b>"))
    await message.reply_text(
        quote(f"<b>✅ {fancy('Page created')}</b>\n\n<code>{link}</code>"),
        disable_web_page_preview=True,
        reply_markup=rows_to_kb([[btn("Open page", url=link)]]),
    )
