import asyncio
import os
import re
import time
import yt_dlp
import aiohttp
import logging
import config  
from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, Playlist

# ----------------- CONFIGURATION -----------------
DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger("BETA BOT HUB | 👑 THE SHIV")

# 🟢 API Configuration
def _clean_url(val):
    val = str(val or "").strip()
    if val.lower().startswith("to "):          # old typo: " to https://..."
        val = val[3:].strip()
    return val.rstrip("/")

def _clean_api_hub_url(val):
    val = _clean_url(val)
    if val and not val.endswith("/v1"):
        val = f"{val}/v1"
    return val

# 1. Beta API Hub Gateway (Lily API Hub - Primary High-Speed Media API)
BETA_API_URL = _clean_api_hub_url(
    os.environ.get("BETA_API_URL")
    or getattr(config, "BETA_API_URL", "")
    or "https://lily-api-hub-production.up.railway.app/v1"
)
BETA_API_KEY = (
    os.environ.get("BETA_API_KEY")
    or getattr(config, "BETA_API_KEY", "")
    or "beta_test_Kut1_pr7Xe2XpKsG3ShKcKFI-uFsB2Iw1lTMJ9w7Z1w"
)

# 2. Secondary API (Shruti)
SHRUTI_API_URL = _clean_url(
    os.environ.get("SHRUTI_API_URL") or getattr(config, "API_URL", "") or "https://api.shrutibots.in"
)
SHRUTI_API_KEY = (
    os.environ.get("SHRUTI_API_KEY") or getattr(config, "API_KEY", "") or "ShrutiBots7Yo5iWyWiyQKME4mrS6r"
)

# Optional cookies.txt for the yt-dlp fallback (age/bot-check videos)
YT_COOKIES = os.environ.get("YT_COOKIES_FILE") or getattr(config, "COOKIES_FILE", "") or "cookies.txt"

_BAD_IDS = {"", "none", "null", "unknown", "unknown title"}
_DL_LOCKS = {}

def time_to_seconds(time_str):
    stringt = str(time_str)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

def get_safe_filename(title: str, default_id: str) -> str:
    if not title:
        return default_id
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def extract_video_id(link: str) -> str:
    link = str(link or "")
    if "youtu.be/" in link:
        return link.split("youtu.be/")[1].split("?")[0]
    elif "v=" in link:
        return link.split("v=")[1].split("&")[0]
    return link

# Helper for Safe Async Execution
async def _async_run(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

# ----------------- DOWNLOADERS -----------------

async def beta_api_download(api_url: str, api_key: str, video_id: str, download_type: str, title: str = None) -> str:
    """Download audio or video using Beta API Hub Gateway (Lily API Hub)."""
    if not api_url or not api_key:
        LOGGER.error("🔴 Beta API Hub URL or API Key is missing!")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, f"beta_{video_id}")
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    lock = _DL_LOCKS.setdefault(file_path, asyncio.Lock())
    async with lock:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path

        tmp_path = file_path + ".part"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "User-Agent": "KavyaMusic/1.0",
        }

        # Endpoints and formats to try in priority order
        if download_type == "video":
            candidates = [
                ("/media/download", {"id": video_id, "type": "video", "format": "mp4"}),
                ("/media/video", {"id": video_id, "quality": "720p"}),
            ]
        else:
            candidates = [
                ("/media/download", {"id": video_id, "format": "mp3"}),
                ("/media/audio", {"id": video_id, "format": "mp3", "bitrate": "320"}),
                ("/media/audio", {"id": video_id, "format": "m4a"}),
            ]

        timeout = aiohttp.ClientTimeout(total=600, connect=20)
        async with aiohttp.ClientSession(headers=headers) as session:
            for ep_path, params in candidates:
                try:
                    url = f"{api_url}{ep_path}"
                    async with session.get(url, params=params, timeout=timeout) as resp:
                        if resp.status == 200:
                            with open(tmp_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(131072):
                                    f.write(chunk)

                            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 50000:
                                os.replace(tmp_path, file_path)
                                LOGGER.info(f"🟢 SUCCESS: Downloaded '{title}' from Beta API Hub ({ep_path})!")
                                return file_path
                        elif resp.status in (401, 403):
                            LOGGER.error(f"🔴 Beta API auth error: HTTP {resp.status}")
                            return None
                        else:
                            LOGGER.warning(f"🟡 Beta API {ep_path} returned HTTP {resp.status}")
                except Exception as e:
                    LOGGER.warning(f"Beta API download error on {ep_path}: {e}")
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
        return None


async def beta_api_search(query: str, limit: int = 1):
    """Search YouTube via Beta API Hub Gateway."""
    if not BETA_API_URL or not BETA_API_KEY:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {BETA_API_KEY}",
            "X-API-Key": BETA_API_KEY,
            "User-Agent": "KavyaMusic/1.0",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"{BETA_API_URL}/media/search",
                params={"query": query},
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results") or []
                    return results[:limit]
    except Exception as e:
        LOGGER.warning(f"Beta API search error: {e}")
    return None


async def beta_api_info(video_id: str):
    """Fetch video metadata via Beta API Hub Gateway."""
    if not BETA_API_URL or not BETA_API_KEY:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {BETA_API_KEY}",
            "X-API-Key": BETA_API_KEY,
            "User-Agent": "KavyaMusic/1.0",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"{BETA_API_URL}/media/info",
                params={"id": video_id},
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        LOGGER.warning(f"Beta API info error: {e}")
    return None


async def external_api_download(api_url: str, api_key: str, video_id: str, download_type: str, title: str = None, api_name: str = "Shruti") -> str:
    if not api_url or not api_key:
        LOGGER.error(f"🔴 {api_name} API URL or API Key is missing!")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, f"{api_name[:3]}_{video_id}")
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    # one download per file at a time (two users asking the same song used to corrupt the file)
    lock = _DL_LOCKS.setdefault(file_path, asyncio.Lock())
    async with lock:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path

        tmp_path = file_path + ".part"
        for attempt in range(1, 3):
            try:
                async with aiohttp.ClientSession() as session:
                    params = {
                        "url": video_id,
                        "type": "audio" if download_type == "audio" else "video",
                        "api_key": api_key,
                    }
                    async with session.get(
                        f"{api_url}/download",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=600, connect=20),
                    ) as resp:
                        if resp.status != 200:
                            LOGGER.error(f"🔴 {api_name} Error: Status {resp.status}")
                            # 401/403/404 will not fix themselves - go straight to fallback
                            if resp.status in (401, 403, 404, 429):
                                return None
                            await asyncio.sleep(1.5)
                            continue

                        with open(tmp_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(131072):
                                f.write(chunk)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 50000:
                    os.replace(tmp_path, file_path)
                    LOGGER.info(f"🟢 SUCCESS: Downloaded '{title}' from {api_name}!")
                    return file_path

                LOGGER.warning(f"🔴 {api_name} returned corrupted/empty file for '{title}'. Rejecting it.")
            except Exception as e:
                LOGGER.error(f"{api_name} Download Error: {e}")
                await asyncio.sleep(1.5)
            finally:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
        return None


def _ytdlp_download_sync(video_id: str, download_type: str, title: str = None):
    """Fallback downloader (blocking). Returns file path or None."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    base = os.path.join(DOWNLOAD_DIR, f"yt_{video_id}_{download_type}")
    final = base + (".mp4" if download_type == "video" else ".m4a")
    if os.path.exists(final) and os.path.getsize(final) > 50000:
        return final

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": base + ".%(ext)s",
        "geo_bypass": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
    }
    if YT_COOKIES and os.path.isfile(YT_COOKIES):
        opts["cookiefile"] = YT_COOKIES
    if download_type == "video":
        # 720p max (VC streams 720p), mp4 container so ffmpeg/pytgcalls can read it
        opts["format"] = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
        if download_type == "video" and not path.endswith(".mp4"):
            path = os.path.splitext(path)[0] + ".mp4"
        for cand in (path, final):
            if cand and os.path.exists(cand) and os.path.getsize(cand) > 50000:
                return cand
    except Exception as e:
        LOGGER.error(f"yt-dlp fallback failed for {video_id} ({download_type}): {e}")
    return None


async def ytdlp_download(video_id: str, download_type: str, title: str = None):
    lock = _DL_LOCKS.setdefault(f"yt_{video_id}_{download_type}", asyncio.Lock())
    async with lock:
        return await _async_run(_ytdlp_download_sync, video_id, download_type, title)


async def _resolve_title(video_id: str, title: str = None):
    if title:
        return title
    try:
        search = VideosSearch(video_id, limit=1)
        res = await search.next()
        if res and res.get("result"):
            return res["result"][0]["title"]
    except Exception:
        pass
    try:
        info = await beta_api_info(video_id)
        if info and info.get("metadata", {}).get("title"):
            return info["metadata"]["title"]
    except Exception:
        pass
    return None


async def _download_media(link: str, title: str, kind: str):
    video_id = extract_video_id(link)
    if str(video_id).strip().lower() in _BAD_IDS or len(str(video_id)) < 3:
        LOGGER.error(f"🔴 Invalid video id '{video_id}' - skipping {kind} download.")
        return None

    title = await _resolve_title(video_id, title)

    # 1. Primary: Beta API Hub Gateway (Lily API Hub)
    if BETA_API_URL and BETA_API_KEY:
        try:
            result = await beta_api_download(BETA_API_URL, BETA_API_KEY, video_id, kind, title)
            if result:
                return result
        except Exception as e:
            LOGGER.warning(f"Beta API Hub failed for {kind} '{title}': {e}")

    # 2. Secondary: Shruti API
    result = await external_api_download(SHRUTI_API_URL, SHRUTI_API_KEY, video_id, kind, title, "Shruti")
    if result:
        return result

    # 3. Fallback: yt-dlp
    LOGGER.warning(f"🟡 External APIs failed for {kind} '{title}'. Trying yt-dlp fallback...")
    result = await ytdlp_download(video_id, kind, title)
    if result:
        LOGGER.info(f"🟢 SUCCESS: Downloaded '{title}' ({kind}) from yt-dlp fallback!")
        return result

    LOGGER.error(f"🔴 All downloaders failed for {kind} '{title}'.")
    return None


async def download_song(link: str, title: str = None) -> str:
    return await _download_media(link, title, "audio")


async def download_video(link: str, title: str = None) -> str:
    return await _download_media(link, title, "video")


# ----------------- YOUTUBE API CLASS -----------------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                for result in response["result"]:
                    title = result["title"]
                    duration_min = result["duration"]
                    thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                    vidid = result["id"]
                    duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
                    return title, duration_min, duration_sec, thumbnail, vidid
        except Exception:
            pass

        # Beta API Hub resolver fallback
        try:
            vid_id = extract_video_id(link)
            if vid_id and len(vid_id) >= 5 and ("youtube" in link or "youtu.be" in link or videoid):
                info = await beta_api_info(vid_id)
                if info and info.get("metadata"):
                    title = info["metadata"].get("title")
                    dur_sec = int(info.get("source", {}).get("duration_seconds") or 0)
                    m, s = divmod(dur_sec, 60)
                    h, m = divmod(m, 60)
                    duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                    thumbnail = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                    if info.get("thumbnails"):
                        thumbnail = info["thumbnails"][0].get("url") or thumbnail
                    return title, duration_min, dur_sec, thumbnail, vid_id
            else:
                search_res = await beta_api_search(link, limit=1)
                if search_res and len(search_res) > 0:
                    r0 = search_res[0]
                    title = r0.get("title")
                    dur_sec = int(r0.get("duration_seconds") or 0)
                    duration_min = r0.get("duration_string") or "0:00"
                    thumbnail = r0.get("thumbnail") or f"https://img.youtube.com/vi/{r0.get('id')}/hqdefault.jpg"
                    vidid = r0.get("id")
                    return title, duration_min, dur_sec, thumbnail, vidid
        except Exception as e:
            LOGGER.warning(f"Beta API details fallback error: {e}")

        try:
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            } 
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"

            r = await _async_run(ydl.extract_info, search_query, download=False)
            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                title = entry.get("title")
                vidid = entry.get("id")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)
                duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                thumbnail = f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg"
                return title, duration_min, dur_sec, thumbnail, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in details: {e}")
        return None, None, None, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["title"]
        except Exception:
            return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["duration"]
        except Exception:
            return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        vid_id_str = link if videoid else extract_video_id(link)
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["thumbnails"][0]["url"].split("?")[0]
        except Exception:
            if vid_id_str and len(vid_id_str) > 5:
                return f"https://img.youtube.com/vi/{vid_id_str}/hqdefault.jpg"
            return "https://telegra.ph/file/2e3d368e77c449c287430.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        try:
            plist = await _async_run(Playlist.get, link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data: continue
            vid = data.get("id")
            if not vid: continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                result = response["result"][0]
                return {
                    "title": result["title"],
                    "link": result["link"],
                    "vidid": result["id"],
                    "duration_min": result["duration"],
                    "thumb": result["thumbnails"][0]["url"].split("?")[0],
                }, result["id"]
        except Exception:
            pass

        # Beta API Hub resolver fallback
        try:
            vid_id = extract_video_id(link)
            if vid_id and len(vid_id) >= 5 and ("youtube" in link or "youtu.be" in link or videoid):
                info = await beta_api_info(vid_id)
                if info and info.get("metadata"):
                    title = info["metadata"].get("title")
                    dur_sec = int(info.get("source", {}).get("duration_seconds") or 0)
                    m, s = divmod(dur_sec, 60)
                    h, m = divmod(m, 60)
                    duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                    thumbnail = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                    if info.get("thumbnails"):
                        thumbnail = info["thumbnails"][0].get("url") or thumbnail
                    return {
                        "title": title,
                        "link": f"https://www.youtube.com/watch?v={vid_id}",
                        "vidid": vid_id,
                        "duration_min": duration_min,
                        "thumb": thumbnail,
                    }, vid_id
            else:
                search_res = await beta_api_search(link, limit=1)
                if search_res and len(search_res) > 0:
                    r0 = search_res[0]
                    vidid = r0.get("id")
                    return {
                        "title": r0.get("title"),
                        "link": f"https://www.youtube.com/watch?v={vidid}",
                        "vidid": vidid,
                        "duration_min": r0.get("duration_string") or "0:00",
                        "thumb": r0.get("thumbnail") or f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                    }, vidid
        except Exception as e:
            LOGGER.warning(f"Beta API track fallback error: {e}")

        try:
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            }
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            r = await _async_run(ydl.extract_info, search_query, download=False)

            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                vidid = entry.get("id")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)

                return {
                    "title": entry.get("title"),
                    "link": f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}",
                    "thumb": f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                }, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in track: {e}")

        return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        ytdl_opts = {
            "quiet": True,
            "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "-x", "16",            
                "-s", "16",            
                "-k", "1M",            
                "--allow-piece-length-change=true"
            ]
        }

        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        formats_available = []

        try:
            r = await _async_run(ydl.extract_info, link, download=False)
            if r and "formats" in r:
                for format in r["formats"]:
                    try:
                        if "dash" not in str(format.get("format", "")).lower():
                            formats_available.append({
                                "format": format.get("format"),
                                "filesize": format.get("filesize"),
                                "format_id": format.get("format_id"),
                                "ext": format.get("ext"),
                                "format_note": format.get("format_note"),
                                "yturl": link,
                            })
                    except Exception: continue
        except Exception:
            pass

        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        raw_vid_str = link if videoid else extract_video_id(link)
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            a = VideosSearch(link, limit=10)
            result = (await a.next()).get("result")
            return result[query_type]["title"], result[query_type]["duration"], result[query_type]["thumbnails"][0]["url"].split("?")[0], result[query_type]["id"]
        except Exception:
            try:
                search_res = await beta_api_search(link, limit=10)
                if search_res and len(search_res) > query_type:
                    item = search_res[query_type]
                    return item.get("title"), item.get("duration_string", "0:00"), item.get("thumbnail"), item.get("id")
            except Exception:
                pass
            fallback_thumb = f"https://img.youtube.com/vi/{raw_vid_str}/hqdefault.jpg" if raw_vid_str and len(raw_vid_str) > 5 else "https://telegra.ph/file/2e3d368e77c449c287430.jpg"
            return "Unknown Title", "0:00", fallback_thumb, "None"

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid: link = self.base + link
        try:
            file_title = title if isinstance(title, str) else None

            if video: downloaded_file = await download_video(link, title=file_title)
            else: downloaded_file = await download_song(link, title=file_title)

            if downloaded_file: return downloaded_file, True
            return None, False
        except Exception as e:
            LOGGER.error(f"Error in YouTubeAPI.download: {e}")
            return None, False

    async def autoplay(self, last_vidid: str, title: str, max_duration: int = None):
        try:
            import random
            search_query = f"{title} official audio"
            valid_choices = []

            try:
                search = VideosSearch(search_query, limit=15)
                result = await search.next()
                if result and result.get("result"):
                    for res in result["result"]:
                        vidid = str(res.get("id") or "")
                        if not vidid or vidid == "None" or vidid == last_vidid: continue

                        dur_str = str(res.get("duration", "0:00"))
                        dur_sec = 0
                        if dur_str and ":" in dur_str:
                            parts = dur_str.split(":")
                            try:
                                if len(parts) == 2: dur_sec = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3: dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except ValueError: pass

                        if dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue

                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(res.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })
            except Exception: pass 

            if not valid_choices:
                ytdl_opts = {
                    "quiet": True, 
                    "extract_flat": True, 
                    "noplaylist": True,
                    "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
                } 
                ydl = yt_dlp.YoutubeDL(ytdl_opts)

                r = await _async_run(ydl.extract_info, f"ytsearch10:{search_query}", download=False)
                if r and "entries" in r:
                    for entry in r["entries"]:
                        vidid = entry.get("id")
                        if not vidid or vidid == last_vidid: continue

                        raw_dur = entry.get("duration", 0)
                        try: dur_sec = int(float(raw_dur)) if raw_dur else 0
                        except (ValueError, TypeError): dur_sec = 0

                        if not dur_sec or dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue

                        m, s = divmod(dur_sec, 60)
                        h, m = divmod(m, 60)
                        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(entry.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })

            if valid_choices: return random.choice(valid_choices)
            return None

        except Exception as e:
            LOGGER.error(f"YouTube Autoplay Function Error: {e}")
            return None

YouTube = YouTubeAPI()
