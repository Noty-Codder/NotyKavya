"""VC logger - voice chat events for every group + the logger group.

* per-chat switch  : /vclogger on | off | (status)   -> short, self-deleting notices in the group
* logger group     : every VC started / ended / invite and every assistant join / leave
                     (honours the global /logger enable|disable switch)
"""

import asyncio
import time

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from KavyaMusic.core.mongo import mongodb
from KavyaMusic.logging import LOGGER
from roohifont import fancy

vcdb = mongodb.vclogger

_state = {}      # chat_id -> bool (cache of the per-chat switch)
_session = {}    # chat_id -> {"since": ts, "tracks": n}   (assistant session)
_vc_open = {}    # chat_id -> ts the voice chat was started
NOTICE_LIFETIME = 25


# ------------------------------------------------------------------ switch
async def is_vclog_on(chat_id) -> bool:
    chat_id = int(chat_id)
    if chat_id not in _state:
        try:
            _state[chat_id] = bool(await vcdb.find_one({"chat_id": chat_id}))
        except Exception:
            _state[chat_id] = False
    return _state[chat_id]


async def set_vclog(chat_id, on: bool):
    chat_id = int(chat_id)
    _state[chat_id] = on
    try:
        if on:
            if not await vcdb.find_one({"chat_id": chat_id}):
                await vcdb.insert_one({"chat_id": chat_id})
        else:
            await vcdb.delete_one({"chat_id": chat_id})
    except Exception as e:
        LOGGER(__name__).warning(f"vclogger db error: {e}")


# ------------------------------------------------------------------ helpers
def _dur(sec):
    sec = max(0, int(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}ʜ {m}ᴍ {s}s"
    if m:
        return f"{m}ᴍ {s}s"
    return f"{s}s"


def _now_str():
    return time.strftime("%d %b %Y • %H:%M:%S UTC", time.gmtime())


def _chat_line(chat):
    title = getattr(chat, "title", None) or "Unknown"
    return f"{title} [<code>{chat.id}</code>]"


def _link_markup(chat):
    username = getattr(chat, "username", None)
    if not username:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(fancy("Open group"), url=f"https://t.me/{username}")]])


async def _logger_on() -> bool:
    if not config.LOGGER_ID:
        return False
    try:
        from KavyaMusic.utils.database import is_on_off
        return bool(await is_on_off(2))
    except Exception:
        return True


async def _delete_later(msg, delay=NOTICE_LIFETIME):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


HEAD = {
    "started": ("🎙", "ᴠᴏɪᴄᴇ ᴄʜᴀᴛ sᴛᴀʀᴛᴇᴅ"),
    "ended": ("🔇", "ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ᴇɴᴅᴇᴅ"),
    "invited": ("📨", "ᴍᴇᴍʙᴇʀs ɪɴᴠɪᴛᴇᴅ ᴛᴏ ᴠᴄ"),
    "joined": ("🎧", "ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ ᴠᴄ"),
    "left": ("👋", "ᴀssɪsᴛᴀɴᴛ ʟᴇꜰᴛ ᴠᴄ"),
}


def build_text(kind, chat, by=None, duration=None, users=None, tracks=None):
    icon, head = HEAD[kind]
    lines = [f"<b>💬 ᴄʜᴀᴛ :</b> {_chat_line(chat)}"]
    if by:
        lines.append(f"<b>👤 ʙʏ :</b> {by}")
    if users:
        lines.append(f"<b>👥 ᴜsᴇʀs :</b> {users}")
    if duration is not None:
        lines.append(f"<b>⏱ ᴅᴜʀᴀᴛɪᴏɴ :</b> {_dur(duration)}")
    if tracks is not None:
        lines.append(f"<b>🎵 ᴛʀᴀᴄᴋs ᴘʟᴀʏᴇᴅ :</b> {tracks}")
    lines.append(f"<b>🕒 ᴛɪᴍᴇ :</b> {_now_str()}")
    return f"<blockquote><b>{icon} {head}</b></blockquote>\n<blockquote>" + "\n".join(lines) + "</blockquote>"


async def log_event(kind, chat, by=None, duration=None, users=None, tracks=None, notice_client=None, notify_chat=True):
    """Send one VC event to the logger group and (if switched on) to the chat itself."""
    from KavyaMusic import app

    text = build_text(kind, chat, by=by, duration=duration, users=users, tracks=tracks)
    markup = _link_markup(chat)

    if await _logger_on() and int(chat.id) != int(config.LOGGER_ID):
        try:
            await app.send_message(config.LOGGER_ID, text, parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True, reply_markup=markup)
        except Exception as e:
            LOGGER(__name__).warning(f"vc log send failed: {e}")

    if notify_chat and kind in ("started", "ended", "invited") and await is_vclog_on(chat.id):
        try:
            msg = await (notice_client or app).send_message(chat.id, text, parse_mode=ParseMode.HTML)
            asyncio.create_task(_delete_later(msg))
        except Exception:
            pass


# ------------------------------------------------------------------ assistant session (called from call.py)
def session_start(chat_id) -> bool:
    """True only for the first call of a new session."""
    chat_id = int(chat_id)
    if chat_id in _session:
        return False
    _session[chat_id] = {"since": time.time(), "tracks": 1}
    return True


def session_track(chat_id):
    s = _session.get(int(chat_id))
    if s:
        s["tracks"] += 1


def session_end(chat_id):
    return _session.pop(int(chat_id), None)


async def _chat_obj(chat_id):
    from KavyaMusic import app
    try:
        return await app.get_chat(int(chat_id))
    except Exception:
        class _C:  # minimal stand-in when the chat can't be fetched
            id = int(chat_id)
            title = "Unknown"
            username = None
        return _C()


async def assistant_joined(chat_id):
    try:
        await log_event("joined", await _chat_obj(chat_id), notify_chat=False)
    except Exception as e:
        LOGGER(__name__).warning(f"vc join log failed: {e}")


async def assistant_left(chat_id, session):
    try:
        await log_event("left", await _chat_obj(chat_id), duration=time.time() - session["since"],
                        tracks=session["tracks"], notify_chat=False)
    except Exception as e:
        LOGGER(__name__).warning(f"vc leave log failed: {e}")


def mark_vc_start(chat_id):
    _vc_open[int(chat_id)] = time.time()
    if len(_vc_open) > 5000:
        _vc_open.clear()


def vc_age(chat_id):
    t = _vc_open.pop(int(chat_id), None)
    return None if t is None else time.time() - t
