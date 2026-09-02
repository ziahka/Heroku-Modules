# meta developer: @exterame

__version__ = (1, 1, 0)

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse

import aiohttp
from herokutl.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    MessageEntityTextUrl,
    MessageEntityUrl,
)
from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"
)


def get_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    termux_path = f"/data/data/com.termux/files/usr/bin/{name}"
    if os.path.isfile(termux_path) and os.access(termux_path, os.X_OK):
        return termux_path

    local_path = os.path.expanduser(f"~/.local/bin/{name}")
    if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
        return local_path

    return None


def parse_timestamp(val: str) -> float | None:
    val = val.strip()
    if not val:
        return None
    try:
        if ":" not in val:
            return max(0.0, float(val))
        parts = [float(p) for p in val.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except (ValueError, TypeError):
        pass
    return None


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def format_duration(seconds: float) -> str:
    sec = int(seconds)
    hrs, remainder = divmod(sec, 3600)
    mins, secs = divmod(remainder, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


async def run_cmd(cmd: list[str], timeout: int = 180) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode(errors="ignore"), stderr.decode(errors="ignore")
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return -1, "", "Timeout"


async def probe_media(file_path: str) -> dict:
    ffprobe = get_bin("ffprobe")
    if not ffprobe:
        return {}

    cmd = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    ret, stdout, _ = await run_cmd(cmd, timeout=20)
    if ret != 0 or not stdout:
        return {}

    try:
        data = json.loads(stdout)
    except Exception:
        return {}

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    fps = None
    if v_stream and "r_frame_rate" in v_stream:
        try:
            num, den = map(int, v_stream["r_frame_rate"].split("/"))
            if den:
                fps = round(num / den, 2)
        except Exception:
            pass

    return {
        "has_video": v_stream is not None,
        "has_audio": a_stream is not None,
        "width": int(v_stream.get("width", 0)) if v_stream else 0,
        "height": int(v_stream.get("height", 0)) if v_stream else 0,
        "duration": float(fmt.get("duration", 0.0) or 0.0),
        "v_codec": v_stream.get("codec_name", "") if v_stream else "",
        "a_codec": a_stream.get("codec_name", "") if a_stream else "",
        "v_bitrate": int(v_stream.get("bit_rate", 0)) if v_stream and v_stream.get("bit_rate") else 0,
        "a_bitrate": int(a_stream.get("bit_rate", 0)) if a_stream and a_stream.get("bit_rate") else 0,
        "format_name": fmt.get("format_name", ""),
        "size": int(fmt.get("size", 0) or 0),
        "fps": fps,
        "sample_rate": a_stream.get("sample_rate", "") if a_stream else "",
        "channels": a_stream.get("channels", 0) if a_stream else 0,
    }


@loader.tds
class SmartMedia(loader.Module):
    """Universal media processing and downloading suite."""

    developer = "@exterame"

    strings = {
        "name": "SmartMedia",
        "_cls_doc": "Universal media processing and downloading suite. Developer: @exterame",
        "downloading": "<b>[Downloading...]</b>",
        "processing": "<b>[Processing...]</b>",
        "uploading": "<b>[Uploading...]</b>",
        "no_media": "<b>[Error]</b> No media found. Reply to a message with media.",
        "no_url": "<b>[Error]</b> Please provide a URL or reply to a message with a link.",
        "dl_downloading": "<b>[Downloading]</b> <code>{}</code>",
        "dl_failed": "<b>[Error]</b> Download failed:\n<code>{}</code>",
        "dl_too_large": "<b>[Error]</b> File size exceeds limit ({}MB > {}MB)",
        "invalid_speed": "<b>[Error]</b> Invalid speed. Specify a value between 0.25 and 4.0.",
        "error_ffmpeg": "<b>[Error]</b> FFmpeg processing failed:\n<code>{}</code>",
        "no_ffmpeg": "<b>[Error]</b> FFmpeg is not installed.\nLinux: apt install ffmpeg\nTermux: pkg install ffmpeg",
        "no_ytdlp": "<b>[Error]</b> yt-dlp is not installed.\nLinux: pip install yt-dlp\nTermux: pkg install yt-dlp",
        "audio_extracted": "<b>[Audio]</b>\nArtist: <code>{}</code>\nTitle: <code>{}</code>",
        "mediainfo_title": "<b>[Media Information]</b>\n",
        "mediainfo_general": "Format: <code>{}</code>\nSize: <code>{}</code>\nDuration: <code>{}</code>\n",
        "mediainfo_video": "\nVideo Stream:\nCodec: <code>{}</code>\nResolution: <code>{}x{}</code>\nFPS: <code>{}</code>\nBitrate: <code>{}</code>\n",
        "mediainfo_audio": "\nAudio Stream:\nCodec: <code>{}</code>\nSample Rate: <code>{} Hz</code>\nChannels: <code>{}</code>\nBitrate: <code>{}</code>\n",
        "inline_dl_title": "Download Media",
        "inline_dl_desc": "Usage: dl <url>",
        "inline_dl_help": "<b>[SmartMedia]</b> Send a valid media URL: <code>@bot dl <url></code>",
    }

    strings_ru = {
        "_cls_doc": "Универсальный инструмент обработки и скачивания медиа.",
        "downloading": "<b>[Скачивание...]</b>",
        "processing": "<b>[Обработка...]</b>",
        "uploading": "<b>[Отправка...]</b>",
        "no_media": "<b>[Ошибка]</b> Медиа не найдено. Ответьте на сообщение с медиа.",
        "no_url": "<b>[Ошибка]</b> Укажите ссылку или ответьте на сообщение со ссылкой.",
        "dl_downloading": "<b>[Загрузка]</b> <code>{}</code>",
        "dl_failed": "<b>[Ошибка]</b> Не удалось скачать медиа:\n<code>{}</code>",
        "dl_too_large": "<b>[Ошибка]</b> Размер файла превышает лимит ({}MB > {}MB)",
        "invalid_speed": "<b>[Ошибка]</b> Неверная скорость. Укажите число от 0.25 до 4.0.",
        "error_ffmpeg": "<b>[Ошибка]</b> Сбой FFmpeg:\n<code>{}</code>",
        "no_ffmpeg": "<b>[Ошибка]</b> FFmpeg не установлен.\nLinux: apt install ffmpeg\nTermux: pkg install ffmpeg",
        "no_ytdlp": "<b>[Ошибка]</b> yt-dlp не установлен.\nLinux: pip install yt-dlp\nTermux: pkg install yt-dlp",
        "audio_extracted": "<b>[Аудио]</b>\nИсполнитель: <code>{}</code>\nНазвание: <code>{}</code>",
        "mediainfo_title": "<b>[Информация о медиа]</b>\n",
        "mediainfo_general": "Формат: <code>{}</code>\nРазмер: <code>{}</code>\nДлительность: <code>{}</code>\n",
        "mediainfo_video": "\nВидео поток:\nКодек: <code>{}</code>\nРазрешение: <code>{}x{}</code>\nFPS: <code>{}</code>\nБитрейт: <code>{}</code>\n",
        "mediainfo_audio": "\nАудио поток:\nКодек: <code>{}</code>\nЧастота: <code>{} Гц</code>\nКаналы: <code>{}</code>\nБитрейт: <code>{}</code>\n",
        "inline_dl_title": "Скачать медиа",
        "inline_dl_desc": "Использование: dl <url>",
        "inline_dl_help": "<b>[SmartMedia]</b> Укажите ссылку: <code>@bot dl <url></code>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "circle_size",
                384,
                lambda: "Resolution of video notes (240, 384, 480, 512)",
                validator=loader.validators.Integer(minimum=128, maximum=720),
            ),
            loader.ConfigValue(
                "circle_max_duration",
                60,
                lambda: "Maximum duration for video notes in seconds",
                validator=loader.validators.Integer(minimum=1, maximum=60),
            ),
            loader.ConfigValue(
                "audio_bitrate",
                "192k",
                lambda: "Bitrate for extracted MP3 audio",
                validator=loader.validators.Choice(["128k", "192k", "256k", "320k"]),
            ),
            loader.ConfigValue(
                "voice_bitrate",
                "64k",
                lambda: "Bitrate for OGG Opus voice notes",
                validator=loader.validators.Choice(["32k", "48k", "64k", "96k"]),
            ),
            loader.ConfigValue(
                "max_download_mb",
                50,
                lambda: "Maximum download size in megabytes",
                validator=loader.validators.Integer(minimum=1, maximum=2000),
            ),
        )

    async def _extract_url(self, message: Message) -> str | None:
        raw_args = utils.get_args_raw(message)
        if raw_args:
            match = URL_REGEX.search(raw_args)
            if match:
                return match.group(0)

        reply = await message.get_reply_message()
        if reply:
            if reply.entities:
                for ent in reply.entities:
                    if isinstance(ent, MessageEntityTextUrl):
                        return ent.url
                    if isinstance(ent, MessageEntityUrl):
                        offset, length = ent.offset, ent.length
                        return reply.raw_text[offset : offset + length]

            if reply.raw_text:
                match = URL_REGEX.search(reply.raw_text)
                if match:
                    return match.group(0)

        return None

    def _resolve_ytdlp(self) -> list[str] | None:
        bin_path = get_bin("yt-dlp")
        if bin_path:
            return [bin_path]
        try:
            import yt_dlp
            return [sys.executable, "-m", "yt_dlp"]
        except ImportError:
            pass
        return None

    @loader.command()
    @loader.tag(aliases=["round", "krug"])
    async def circle(self, message: Message):
        """[start] [end] - Convert replied video/photo/GIF into a circular video note"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        args = utils.get_args(message)
        start_time = None
        end_time = None
        if len(args) == 1:
            end_time = parse_timestamp(args[0])
        elif len(args) >= 2:
            start_time = parse_timestamp(args[0])
            end_time = parse_timestamp(args[1])

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)
            size = self.config["circle_size"]
            max_dur = self.config["circle_max_duration"]
            out_file = os.path.join(tmp_dir, "circle.mp4")

            duration_to_cut = max_dur
            if start_time is not None and end_time is not None:
                duration_to_cut = min(max_dur, max(1.0, end_time - start_time))
            elif end_time is not None:
                duration_to_cut = min(max_dur, max(1.0, end_time))

            crop_filter = f"[0:v]crop=min(iw\\,ih):min(iw\\,ih),scale={size}:{size}[v]"

            cmd = [ffmpeg, "-y"]
            if start_time is not None:
                cmd.extend(["-ss", str(start_time)])

            if not info.get("has_video") or info.get("duration", 0) <= 0.05:
                cmd.extend([
                    "-loop", "1",
                    "-i", downloaded,
                    "-f", "lavfi",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-t", "3",
                    "-filter_complex", crop_filter,
                    "-map", "[v]",
                    "-map", "1:a",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-c:a", "aac",
                    "-b:a", "64k",
                    "-movflags", "+faststart",
                    out_file,
                ])
            else:
                cmd.extend(["-t", str(duration_to_cut), "-i", downloaded])
                if not info.get("has_audio"):
                    cmd.extend([
                        "-f", "lavfi",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-filter_complex", crop_filter,
                        "-map", "[v]",
                        "-map", "1:a",
                        "-shortest",
                    ])
                else:
                    cmd.extend([
                        "-filter_complex", crop_filter,
                        "-map", "[v]",
                        "-map", "0:a",
                    ])

                cmd.extend([
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-crf", "24",
                    "-c:a", "aac",
                    "-b:a", "64k",
                    "-movflags", "+faststart",
                    out_file,
                ])

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                video_note=True,
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(aliases=["togv", "tovoice"])
    async def voice(self, message: Message):
        """[start] [end] - Convert replied audio/video/round note into a voice note"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        args = utils.get_args(message)
        start_time = None
        end_time = None
        if len(args) == 1:
            end_time = parse_timestamp(args[0])
        elif len(args) >= 2:
            start_time = parse_timestamp(args[0])
            end_time = parse_timestamp(args[1])

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            out_file = os.path.join(tmp_dir, "voice.ogg")

            cmd = [ffmpeg, "-y"]
            if start_time is not None:
                cmd.extend(["-ss", str(start_time)])
            if end_time is not None:
                duration = end_time - (start_time or 0.0)
                if duration > 0:
                    cmd.extend(["-t", str(duration)])

            cmd.extend([
                "-i", downloaded,
                "-vn",
                "-c:a", "libopus",
                "-b:a", self.config["voice_bitrate"],
                "-vbr", "on",
                "-application", "voip",
                out_file,
            ])

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                voice_note=True,
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(aliases=["toaudio", "mp3"])
    async def audio(self, message: Message):
        """[title] [| artist] - Extract audio track from replied video/voice/round note"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        raw_args = utils.get_args_raw(message)
        title = "Audio Track"
        performer = "SmartMedia"
        if raw_args:
            if "|" in raw_args:
                parts = raw_args.split("|", 1)
                title = parts[0].strip() or title
                performer = parts[1].strip() or performer
            else:
                title = raw_args.strip()

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            out_file = os.path.join(tmp_dir, "extracted.mp3")

            cmd = [
                ffmpeg,
                "-y",
                "-i",
                downloaded,
                "-vn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                self.config["audio_bitrate"],
                "-metadata",
                f"title={title}",
                "-metadata",
                f"artist={performer}",
                out_file,
            ]

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            info = await probe_media(out_file)
            duration = int(info.get("duration", 0))

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                caption=self.strings("audio_extracted").format(performer, title),
                attributes=[
                    DocumentAttributeAudio(
                        duration=duration,
                        voice=False,
                        title=title,
                        performer=performer,
                    )
                ],
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(alias="tomp4")
    async def tovideo(self, message: Message):
        """- Convert round video note, GIF, sticker, or WebM to standard MP4 video"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)
            out_file = os.path.join(tmp_dir, "converted.mp4")

            cmd = [ffmpeg, "-y", "-i", downloaded]
            if not info.get("has_audio"):
                cmd.extend([
                    "-f", "lavfi",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                ])
            else:
                cmd.extend(["-map", "0:v", "-map", "0:a"])

            cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                out_file,
            ])

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            out_info = await probe_media(out_file)
            duration = int(out_info.get("duration", 0))
            w = out_info.get("width", 0)
            h = out_info.get("height", 0)

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                attributes=[
                    DocumentAttributeVideo(
                        duration=duration,
                        w=w,
                        h=h,
                        supports_streaming=True,
                    )
                ],
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(alias="sticker")
    async def tosticker(self, message: Message):
        """- Convert replied photo or short video to Telegram sticker format (WebP / WebM)"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)

            if info.get("has_video") and info.get("duration", 0) > 0.1:
                out_file = os.path.join(tmp_dir, "sticker.webm")
                cmd = [
                    ffmpeg, "-y",
                    "-i", downloaded,
                    "-t", "3",
                    "-vf", "scale=w=512:h=512:force_original_aspect_ratio=decrease",
                    "-c:v", "libvpx-vp9",
                    "-b:v", "256k",
                    "-crf", "30",
                    "-an",
                    out_file,
                ]
            else:
                out_file = os.path.join(tmp_dir, "sticker.webp")
                cmd = [
                    ffmpeg, "-y",
                    "-i", downloaded,
                    "-vframes", "1",
                    "-vf", "scale=w=512:h=512:force_original_aspect_ratio=decrease",
                    "-vcodec", "libwebp",
                    "-lossless", "0",
                    "-compression_level", "4",
                    "-q:v", "90",
                    out_file,
                ]

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(aliases=["fast", "slow"])
    async def speed(self, message: Message):
        """<multiplier> - Change playback speed of replied media (0.25 - 4.0)"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        raw_args = utils.get_args_raw(message)
        if not raw_args:
            await utils.answer(message, self.strings("invalid_speed"))
            return

        try:
            factor = float(raw_args.split()[0].replace(",", "."))
            if factor < 0.25 or factor > 4.0:
                raise ValueError
        except ValueError:
            await utils.answer(message, self.strings("invalid_speed"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        is_voice = bool(getattr(reply, "voice", False))
        is_video_note = bool(getattr(reply, "video_note", False))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)

            atempo_filters = []
            cur_f = factor
            while cur_f > 2.0:
                atempo_filters.append("atempo=2.0")
                cur_f /= 2.0
            while cur_f < 0.5:
                atempo_filters.append("atempo=0.5")
                cur_f /= 0.5
            atempo_filters.append(f"atempo={cur_f:.4f}")
            af_str = ",".join(atempo_filters)

            cmd = [ffmpeg, "-y", "-i", downloaded]

            if info.get("has_video"):
                out_ext = "mp4"
                vf_str = f"setpts={1 / factor:.4f}*PTS"
                cmd.extend(["-filter:v", vf_str])
                if info.get("has_audio"):
                    cmd.extend(["-filter:a", af_str, "-c:a", "aac", "-b:a", "128k"])
                cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"])
            else:
                out_ext = "ogg" if is_voice else "mp3"
                cmd.extend(["-filter:a", af_str])
                if is_voice:
                    cmd.extend(["-c:a", "libopus", "-b:a", self.config["voice_bitrate"]])
                else:
                    cmd.extend(["-c:a", "libmp3lame", "-b:a", self.config["audio_bitrate"]])

            out_file = os.path.join(tmp_dir, f"speed_{factor}.{out_ext}")
            cmd.append(out_file)

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            kwargs = {"reply_to": reply_to}
            if is_video_note:
                kwargs["video_note"] = True
            elif is_voice:
                kwargs["voice_note"] = True

            await message.client.send_file(message.peer_id, out_file, **kwargs)
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(alias="rev")
    async def reverse(self, message: Message):
        """- Reverse playback of replied media (video/audio/voice/circle)"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        is_voice = bool(getattr(reply, "voice", False))
        is_video_note = bool(getattr(reply, "video_note", False))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)

            cmd = [ffmpeg, "-y", "-i", downloaded]

            if info.get("has_video"):
                out_ext = "mp4"
                cmd.extend(["-vf", "reverse"])
                if info.get("has_audio"):
                    cmd.extend(["-af", "areverse", "-c:a", "aac", "-b:a", "128k"])
                cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"])
            else:
                out_ext = "ogg" if is_voice else "mp3"
                cmd.extend(["-af", "areverse"])
                if is_voice:
                    cmd.extend(["-c:a", "libopus", "-b:a", self.config["voice_bitrate"]])
                else:
                    cmd.extend(["-c:a", "libmp3lame", "-b:a", self.config["audio_bitrate"]])

            out_file = os.path.join(tmp_dir, f"reversed.{out_ext}")
            cmd.append(out_file)

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            kwargs = {"reply_to": reply_to}
            if is_video_note:
                kwargs["video_note"] = True
            elif is_voice:
                kwargs["voice_note"] = True

            await message.client.send_file(message.peer_id, out_file, **kwargs)
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(alias="gif")
    async def togif(self, message: Message):
        """- Convert replied video or video note into an animated GIF"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            out_file = os.path.join(tmp_dir, "animation.mp4")

            cmd = [
                ffmpeg, "-y",
                "-i", downloaded,
                "-an",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-movflags", "+faststart",
                out_file,
            ]

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            await message.client.send_file(
                message.peer_id,
                out_file,
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(alias="compress")
    async def vcompress(self, message: Message):
        """[crf 18-35] - Compress replied video to reduce file size"""
        ffmpeg = get_bin("ffmpeg")
        if not ffmpeg:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        raw_args = utils.get_args_raw(message) or ""
        crf = "28"
        if raw_args and raw_args.strip().isdigit():
            val = int(raw_args.strip())
            if 18 <= val <= 35:
                crf = str(val)

        status = await utils.answer(message, self.strings("downloading"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            await utils.answer(status, self.strings("processing"))
            info = await probe_media(downloaded)
            orig_size = os.path.getsize(downloaded)
            out_file = os.path.join(tmp_dir, "compressed.mp4")

            cmd = [ffmpeg, "-y", "-i", downloaded]
            if info.get("has_audio"):
                cmd.extend(["-c:a", "aac", "-b:a", "64k"])
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", crf,
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_file,
            ])

            ret, _, err = await run_cmd(cmd)
            if ret != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
                await utils.answer(status, self.strings("error_ffmpeg").format(err[-300:]))
                return

            new_size = os.path.getsize(out_file)
            saved_pct = round((1 - (new_size / max(1, orig_size))) * 100, 1)

            await utils.answer(status, self.strings("uploading"))
            reply_to = reply.id if reply else getattr(message, "reply_to_msg_id", None)
            caption = f"<b>[Compressed]</b> {format_bytes(orig_size)} -> {format_bytes(new_size)} (-{saved_pct}%)"
            await message.client.send_file(
                message.peer_id,
                out_file,
                caption=caption,
                reply_to=reply_to,
            )
            with contextlib.suppress(Exception):
                await status.delete()

    @loader.command()
    @loader.tag(aliases=["vdl", "tt", "reels", "yt"])
    async def dl(self, message: Message):
        """[url] [-a] - Download media from TikTok, Reels, YouTube, Twitter/X, Reddit, etc."""
        url = await self._extract_url(message)
        if not url:
            await utils.answer(message, self.strings("no_url"))
            return

        raw_args = utils.get_args_raw(message) or ""
        audio_only = "-a" in raw_args.split() or "--audio" in raw_args.split()

        status = await utils.answer(message, self.strings("dl_downloading").format(url))

        ytdlp_cmd = self._resolve_ytdlp()
        max_mb = self.config["max_download_mb"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_template = os.path.join(tmp_dir, "media.%(ext)s")
            files = []
            title = "Downloaded Media"
            uploader = "SmartMedia"
            err = ""

            if ytdlp_cmd:
                meta_cmd = [*ytdlp_cmd, "--dump-single-json", "--no-warnings", "--no-playlist", url]
                m_ret, m_out, _ = await run_cmd(meta_cmd, timeout=30)
                if m_ret == 0 and m_out:
                    with contextlib.suppress(Exception):
                        meta_data = json.loads(m_out)
                        title = meta_data.get("title", title)
                        uploader = meta_data.get("uploader", uploader)

                cmd = [
                    *ytdlp_cmd,
                    "--no-playlist",
                    "--no-warnings",
                    "--max-filesize", f"{max_mb}M",
                    "--output", out_template,
                ]

                if audio_only:
                    cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "192k"])
                else:
                    cmd.extend([
                        "-f", "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                        "--merge-output-format", "mp4",
                    ])

                cmd.append(url)
                ret, _, err = await run_cmd(cmd, timeout=240)

                files = [
                    os.path.join(tmp_dir, f)
                    for f in os.listdir(tmp_dir)
                    if not f.endswith(".part") and not f.endswith(".ytdl")
                ]

            if not files and "tiktok.com" in url:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"https://www.tikwm.com/api/?url={url}"
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                t_data = await resp.json()
                                play_url = t_data.get("data", {}).get("play")
                                if play_url:
                                    title = t_data.get("data", {}).get("title", "TikTok Video")
                                    uploader = t_data.get("data", {}).get("author", {}).get("nickname", "TikTok")
                                    fb_file = os.path.join(tmp_dir, "tiktok.mp4")
                                    async with session.get(play_url, timeout=aiohttp.ClientTimeout(total=60)) as vid_resp:
                                        if vid_resp.status == 200:
                                            with open(fb_file, "wb") as f:
                                                while chunk := await vid_resp.content.read(65536):
                                                    f.write(chunk)
                                            files = [fb_file]
                except Exception as fb_exc:
                    logger.warning("TikWM fallback failed: %s", fb_exc)

            if not files:
                if not ytdlp_cmd:
                    await utils.answer(status, self.strings("no_ytdlp"))
                else:
                    await utils.answer(status, self.strings("dl_failed").format(err[-300:] or "Unknown error"))
                return

            downloaded_file = files[0]
            f_size = os.path.getsize(downloaded_file)
            if f_size > max_mb * 1024 * 1024:
                await utils.answer(
                    status,
                    self.strings("dl_too_large").format(f_size // (1024 * 1024), max_mb),
                )
                return

            await utils.answer(status, self.strings("uploading"))
            caption = (
                f"<b>{utils.escape_html(title)}</b>\n"
                f"<i>{utils.escape_html(uploader)}</i>\n"
                f"<a href='{url}'>{urlparse(url).netloc}</a>"
            )

            reply_to = getattr(message, "reply_to_msg_id", None)
            if audio_only:
                info = await probe_media(downloaded_file)
                await message.client.send_file(
                    message.peer_id,
                    downloaded_file,
                    caption=caption,
                    attributes=[
                        DocumentAttributeAudio(
                            duration=int(info.get("duration", 0)),
                            voice=False,
                            title=title,
                            performer=uploader,
                        )
                    ],
                    reply_to=reply_to,
                )
            else:
                await message.client.send_file(
                    message.peer_id,
                    downloaded_file,
                    caption=caption,
                    reply_to=reply_to,
                )

            with contextlib.suppress(Exception):
                await status.delete()

    @loader.inline_handler()
    async def dl_inline_handler(self, query):
        """Download media via inline query"""
        raw = query.query.strip()
        if raw.lower().startswith("dl"):
            raw = raw[2:].strip()

        match = URL_REGEX.search(raw)
        if not match:
            return {
                "title": self.strings("inline_dl_title"),
                "description": self.strings("inline_dl_desc"),
                "message": self.strings("inline_dl_help"),
            }

        url = match.group(0)
        title = "Media Download"
        uploader = "SmartMedia"
        direct_video = None

        if "tiktok.com" in url:
            try:
                async with aiohttp.ClientSession() as session:
                    api_url = f"https://www.tikwm.com/api/?url={url}"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            t_data = await resp.json()
                            play = t_data.get("data", {}).get("play")
                            if play:
                                direct_video = play
                                title = t_data.get("data", {}).get("title", title)
                                uploader = t_data.get("data", {}).get("author", {}).get("nickname", uploader)
            except Exception:
                pass

        if not direct_video:
            ytdlp_cmd = self._resolve_ytdlp()
            if ytdlp_cmd:
                meta_cmd = [*ytdlp_cmd, "--dump-single-json", "--no-warnings", "--no-playlist", url]
                ret, out, _ = await run_cmd(meta_cmd, timeout=20)
                if ret == 0 and out:
                    with contextlib.suppress(Exception):
                        data = json.loads(out)
                        title = data.get("title", title)
                        uploader = data.get("uploader", uploader)
                        formats = data.get("formats", [])
                        for f in formats:
                            if f.get("ext") == "mp4" and f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                                direct_video = f["url"]
                        if not direct_video and data.get("url"):
                            direct_video = data["url"]

        caption = (
            f"<b>{utils.escape_html(title)}</b>\n"
            f"<i>{utils.escape_html(uploader)}</i>\n"
            f"<a href='{url}'>{urlparse(url).netloc}</a>"
        )

        if direct_video and direct_video.startswith("http"):
            return {
                "title": title[:64],
                "description": f"By {uploader}",
                "video": direct_video,
                "caption": caption,
            }

        return {
            "title": title[:64],
            "description": f"Ready: {uploader}",
            "message": caption,
        }

    @loader.command()
    @loader.tag(alias="minfo")
    async def mediainfo(self, message: Message):
        """- Show detailed technical metadata of replied media file"""
        ffprobe = get_bin("ffprobe")
        if not ffprobe:
            await utils.answer(message, self.strings("no_ffmpeg"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("downloading"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = os.path.join(tmp_dir, "input_media")
            downloaded = await message.client.download_media(reply, file=in_file)
            if not downloaded or not os.path.exists(downloaded):
                await utils.answer(status, self.strings("no_media"))
                return

            info = await probe_media(downloaded)
            if not info:
                await utils.answer(status, self.strings("no_media"))
                return

            text = self.strings("mediainfo_title")
            text += self.strings("mediainfo_general").format(
                info.get("format_name", "N/A"),
                format_bytes(info.get("size", 0)),
                format_duration(info.get("duration", 0)),
            )

            if info.get("has_video"):
                v_bitrate = (
                    f"{info['v_bitrate'] // 1000} kbps"
                    if info.get("v_bitrate")
                    else "N/A"
                )
                text += self.strings("mediainfo_video").format(
                    info.get("v_codec", "N/A"),
                    info.get("width", 0),
                    info.get("height", 0),
                    info.get("fps") or "N/A",
                    v_bitrate,
                )

            if info.get("has_audio"):
                a_bitrate = (
                    f"{info['a_bitrate'] // 1000} kbps"
                    if info.get("a_bitrate")
                    else "N/A"
                )
                text += self.strings("mediainfo_audio").format(
                    info.get("a_codec", "N/A"),
                    info.get("sample_rate", "N/A"),
                    info.get("channels", "N/A"),
                    a_bitrate,
                )

            await utils.answer(status, text)
