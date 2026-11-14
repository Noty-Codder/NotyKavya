from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message

from KavyaMusic import app
from KavyaMusic.misc import SUDOERS
from KavyaMusic.utils import vclog
from roohifont import fancy, quote
from config import BANNED_USERS


async def _is_admin(message: Message) -> bool:
    """Group admins / owner / sudoers. (Works even when nothing is playing.)"""
    user = message.from_user
    if user is None:
        return False
    if user.id in SUDOERS:
        return True
    try:
        member = await app.get_chat_member(message.chat.id, user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


@app.on_message(filters.command(["vclogger", "vclog"]) & filters.group & ~BANNED_USERS)
async def vclogger_cmd(client, message: Message):
    chat_id = message.chat.id
    arg = message.command[1].lower() if len(message.command) > 1 else ""
    if arg in ("on", "enable", "off", "disable") and not await _is_admin(message):
        return await message.reply_text(quote(f"<b>❌ {fancy('Only group admins can change this.')}</b>"))
    if arg in ("on", "enable"):
        await vclog.set_vclog(chat_id, True)
        return await message.reply_text(quote(f"<b>🎙 {fancy('VC logger')} : ✅ {fancy('enabled')}</b>\n"
                                              f"<b>{fancy('VC start / end / invites will be logged here.')}</b>"))
    if arg in ("off", "disable"):
        await vclog.set_vclog(chat_id, False)
        return await message.reply_text(quote(f"<b>🎙 {fancy('VC logger')} : ❌ {fancy('disabled')}</b>"))

    on = await vclog.is_vclog_on(chat_id)
    state = f"✅ {fancy('enabled')}" if on else f"❌ {fancy('disabled')}"
    await message.reply_text(quote(f"<b>🎙 {fancy('VC logger')} : {state}</b>\n"
                                   f"<b>{fancy('Use')}</b> <code>/vclogger on</code> | <code>/vclogger off</code>"))


@app.on_message(filters.video_chat_started, group=40)
async def vc_started(client, message: Message):
    vclog.mark_vc_start(message.chat.id)
    by = message.from_user.mention if message.from_user else None
    await vclog.log_event("started", message.chat, by=by, notice_client=client)


@app.on_message(filters.video_chat_ended, group=41)
async def vc_ended(client, message: Message):
    dur = getattr(message.video_chat_ended, "duration", None)
    if dur is None:
        dur = vclog.vc_age(message.chat.id)
    else:
        vclog.vc_age(message.chat.id)
    by = message.from_user.mention if message.from_user else None
    await vclog.log_event("ended", message.chat, by=by, duration=dur, notice_client=client)


@app.on_message(filters.video_chat_members_invited, group=42)
async def vc_invited(client, message: Message):
    try:
        users = ", ".join(u.mention for u in message.video_chat_members_invited.users[:10])
    except Exception:
        users = None
    by = message.from_user.mention if message.from_user else None
    await vclog.log_event("invited", message.chat, by=by, users=users, notice_client=client)
