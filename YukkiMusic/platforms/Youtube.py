import os
import random
import asyncio
import httpx
import yt_dlp
import re
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from YukkiMusic.utils.exceptions import DownloadError
from YukkiMusic.utils.formatters import time_to_seconds


# Improved cookies function
def cookies():
    cookie_dir = "YukkiMusic/utils/cookies"
    cookies_files = [f for f in os.listdir(cookie_dir) if f.endswith(".txt")]

    if not cookies_files:
        raise FileNotFoundError("No cookie files found in directory")

    cookie_file = os.path.join(cookie_dir, random.choice(cookies_files))
    return cookie_file


# Improved directory check/creation
def ensure_download_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")


# Unified download logic
async def download(videoid, video: bool = False):
    url = f"https://invidious.jing.rocks/api/v1/videos/{videoid}"

    async with httpx.AsyncClient(http2=True) as client:
        response = await client.get(url)

    response_data = response.json()
    formats = response_data.get("adaptiveFormats", [])

    download_url = None
    path = None

    ensure_download_dir("downloads")

    if video:
        path = os.path.join("downloads", f"{videoid}.mp4")
        formats = response_data.get("formatStreams", [])
        for fmt in formats:
            download_url = fmt.get("url")
            if download_url:
                break
    else:
        path = os.path.join("downloads", f"{videoid}.m4a")
        for fmt in formats:
            if fmt.get("audioQuality") == "AUDIO_QUALITY_MEDIUM":
                download_url = fmt.get("url")
                if download_url:
                    break

    if not download_url:
        raise ValueError("No suitable format found")

    command = f'yt-dlp -o "{path}" "{download_url}"'
    await shell_cmd(command)

    if os.path.isfile(path):
        return path
    else:
        raise Exception(f"Download failed for video: {videoid}")


# Simplified download function with unified logic
async def api_download(videoid, video=False):
    try:
        return await download(videoid, video)
    except Exception as e:
        raise DownloadError(f"Failed to download video {videoid}: {str(e)}")


# Refined YouTube download function
async def youtube_download(videoid, is_video=False):
    try:
        path = await api_download(videoid, is_video)
        return path
    except Exception as e:
        return f"Error downloading {videoid}: {str(e)}"


# Simplified YouTubeAPI class usage
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"

    async def exists(self, link: str):
        return re.search(self.regex, link) is not None

    async def url(self, message_1: Message) -> str:
        text = message_1.text or message_1.caption
        offset = None
        length = None
        if message_1.entities:
            for entity in message_1.entities:
                if entity.type == MessageEntityType.URL:
                    offset, length = entity.offset, entity.length
                    break
        return text[offset: offset + length] if offset else None

    async def details(self, link: str):
        results = VideosSearch(link, limit=1)
        result = (await results.next())["result"][0]

        title = result["title"]
        duration_min = result["duration"]
        thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        vidid = result["id"]
        duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0

        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str):
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["title"]

    async def duration(self, link: str):
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["duration"]

    async def thumbnail(self, link: str):
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str):
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies",
            cookies(),
            "-g",
            "-f",
            "best[height<=?720][width<=?1280]",
            link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link, limit):
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download --cookies {cookies()} {link}"
        )
        result = playlist.split("\n")
        return [item for item in result if item]

    async def track(self, link: str):
        results = VideosSearch(link, limit=1)
        result = (await results.next())["result"][0]

        track_details = {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result["duration"],
            "thumb": result["thumbnails"][0]["url"].split("?")[0],
        }
        return track_details  # Return only the dictionary

    async def formats(self, link: str):
        ytdl_opts = {"quiet": True, "cookiefile": cookies()}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                if "dash" not in str(format["format"]).lower():
                    formats_available.append({
                        "format": format["format"],
                        "filesize": format.get("filesize"),
                        "format_id": format["format_id"],
                        "ext": format["ext"],
                        "format_note": format["format_note"],
                        "yturl": link,
                    })
        return formats_available, link

    async def slider(self, link: str, query_type: int):
        results = VideosSearch(link, limit=10)
        result = (await results.next())["result"][query_type]
        return result["title"], result["duration"], result["thumbnails"][0]["url"].split("?")[0], result["id"]

    async def download(self, link: str, video=False, format_id=None, title=None):
        vidid = re.search(r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|v\/|embed\/|.+\?v=)([^&\n]+)", link).group(1)
        path = await youtube_download(vidid, video)
        return path

