# meta developer: @exterame

__version__ = (1, 0, 0)

import asyncio
import io
import logging
import math
import os
import re
import secrets
import string
import tempfile
import urllib.parse
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiohttp
from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

ZERO_WIDTH_CHARS = {
    0x200B: "Zero-Width Space (ZWSP)",
    0x200C: "Zero-Width Non-Joiner (ZWNJ)",
    0x200D: "Zero-Width Joiner (ZWJ)",
    0x200E: "Left-To-Right Mark (LRM)",
    0x200F: "Right-To-Left Mark (RLM)",
    0x202A: "Left-To-Right Embedding (LRE)",
    0x202B: "Right-To-Left Embedding (RLE)",
    0x202C: "Pop Directional Formatting (PDF)",
    0x202D: "Left-To-Right Override (LRO)",
    0x202E: "Right-To-Left Override (RLO)",
    0x2060: "Word Joiner (WJ)",
    0x2061: "Function Application",
    0x2062: "Invisible Times",
    0x2063: "Invisible Separator",
    0x2064: "Invisible Plus",
    0xFEFF: "Byte Order Mark (BOM)",
    0x00AD: "Soft Hyphen (SHY)",
    0x034F: "Combining Grapheme Joiner (CGJ)",
    0x180E: "Mongolian Vowel Separator",
}

ZERO_WIDTH_RE = re.compile(
    "[" + "".join(re.escape(chr(code)) for code in ZERO_WIDTH_CHARS) + "]"
)

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_brand",
    "si",
    "feature",
    "fbclid",
    "gclid",
    "yclid",
    "msclkid",
    "twclid",
    "dclid",
    "igshid",
    "share_id",
    "ref",
    "referrer",
    "ref_src",
    "ref_url",
    "_openstat",
    "spm",
    "from_source",
    "tracking_id",
    "click_id",
    "aff_id",
    "soc_src",
    "soc_trk",
    "s_kwcid",
    "sc_cid",
    "mkt_tok",
    "trk",
    "igsh",
}

REDIRECT_DOMAINS = {
    "google.com": ("/url", ["q", "url"]),
    "www.google.com": ("/url", ["q", "url"]),
    "vk.com": ("/away.php", ["to"]),
    "www.vk.com": ("/away.php", ["to"]),
    "youtube.com": ("/redirect", ["q"]),
    "www.youtube.com": ("/redirect", ["q"]),
}

SHORTENER_DOMAINS = {
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "clck.ru",
    "cutt.ly",
    "is.gd",
    "goo.gl",
    "rb.gy",
    "ow.ly",
    "buff.ly",
}


def clean_url_params(url_str: str) -> str:
    parsed = urlparse(url_str)
    if not parsed.netloc:
        return url_str

    path = parsed.path
    qs = parse_qsl(parsed.query, keep_blank_values=False)

    netloc_lower = parsed.netloc.lower()
    for dom, (red_path, keys) in REDIRECT_DOMAINS.items():
        if netloc_lower == dom and path.startswith(red_path):
            for k, val in qs:
                if k in keys:
                    return clean_url_params(val)

    filtered_qs = [
        (k, val)
        for k, val in qs
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    new_query = urlencode(filtered_qs)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


async def unshorten_url(url_str: str) -> str:
    parsed = urlparse(url_str)
    if parsed.netloc.lower() in SHORTENER_DOMAINS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url_str, allow_redirects=True, timeout=5
                ) as resp:
                    if resp.url:
                        return str(resp.url)
        except Exception:
            pass
    return url_str


@loader.tds
class exteraStealth(loader.Module):
    """Privacy, anti-leak inspection, metadata stripping and stealth tools"""

    developer = "@exterame"

    strings = {
        "name": "exteraStealth",
        "_cls_doc": "Privacy, anti-leak inspection, metadata stripping and stealth tools. Developer: @exterame",
        "cleanurl_usage": "<b>[!]</b> Provide URL or reply to message with links.",
        "cleanurl_cleaned": (
            "<b>[+] Cleaned URL:</b>\n"
            "<code>{url}</code>"
        ),
        "cleanurl_multi": (
            "<b>[+] Cleaned URLs ({count}):</b>\n\n"
            "{links}"
        ),
        "unmark_usage": "<b>[!]</b> Reply to a message or provide text to scan for hidden watermarks.",
        "unmark_clean": "<b>[+]</b> No hidden zero-width marks or fingerprinting bytes detected.",
        "unmark_found": (
            "<b>[!] Hidden watermarks detected ({count} characters):</b>\n"
            "{details}\n\n"
            "<b>[+] Sanitized text:</b>\n"
            "<blockquote>{clean_text}</blockquote>"
        ),
        "strip_usage": "<b>[!]</b> Reply to photo, video, or document to strip metadata.",
        "strip_processing": "<b>[~]</b> Stripping metadata and anonymizing file...",
        "strip_done": "<b>[+]</b> Metadata completely purged. File anonymized.",
        "strip_failed": "<b>[!]</b> Failed to process media metadata.",
        "peek_usage": "<b>[!]</b> Specify message link (e.g. t.me/channel/123) or reply to a message.",
        "peek_error": "<b>[!]</b> Failed to fetch message: <code>{}</code>",
        "peek_info": (
            "<b>[>] Ghost Inspection</b>\n\n"
            "<b>Source:</b> <code>{chat}</code>\n"
            "<b>Sender:</b> <code>{sender}</code>\n"
            "<b>Date:</b> <code>{date}</code>\n"
            "<b>Views:</b> <code>{views}</code>\n"
            "<b>Media:</b> <code>{media}</code>\n\n"
            "<b>Content:</b>\n"
            "<blockquote>{text}</blockquote>"
        ),
        "ghost_usage": "<b>[!]</b> Usage: <code>.ghost &lt;seconds&gt; &lt;text&gt;</code>",
        "ghost_sent": "<b>[~]</b> Stealth message self-destructing in {sec}s...",
        "pw_generated": (
            "<b>[+] Generated Secret Key</b>\n\n"
            "<b>Value:</b> <code>{password}</code>\n"
            "<b>Length:</b> <code>{length}</code> characters\n"
            "<b>Entropy:</b> <code>{entropy:.1f}</code> bits"
        ),
    }

    strings_ru = {
        "_cls_doc": "Инструменты приватности, очистки ссылок, защиты от сливов и удаления метаданных. Разработчик: @exterame",
        "cleanurl_usage": "<b>[!]</b> Укажите ссылку или ответьте на сообщение с ссылками.",
        "cleanurl_cleaned": (
            "<b>[+] Очищенная ссылка:</b>\n"
            "<code>{url}</code>"
        ),
        "cleanurl_multi": (
            "<b>[+] Очищено ссылок ({count}):</b>\n\n"
            "{links}"
        ),
        "unmark_usage": "<b>[!]</b> Ответьте на сообщение или введите текст для проверки на скрытые метки.",
        "unmark_clean": "<b>[+]</b> Скрытых невидимых символов и цифровых меток не обнаружено.",
        "unmark_found": (
            "<b>[!] Обнаружены скрытые метки ({count} шт):</b>\n"
            "{details}\n\n"
            "<b>[+] Очищенный текст:</b>\n"
            "<blockquote>{clean_text}</blockquote>"
        ),
        "strip_usage": "<b>[!]</b> Ответьте на фото, видео или документ для удаления метаданных.",
        "strip_processing": "<b>[~]</b> Очистка метаданных и анонимизация файла...",
        "strip_done": "<b>[+]</b> Метаданные полностью удалены. Файл анонимизирован.",
        "strip_failed": "<b>[!]</b> Не удалось обработать метаданные медиафайла.",
        "peek_usage": "<b>[!]</b> Укажите ссылку на пост (t.me/channel/123) или ответьте на сообщение.",
        "peek_error": "<b>[!]</b> Не удалось прочитать сообщение: <code>{}</code>",
        "peek_info": (
            "<b>[>] Фантомный просмотр</b>\n\n"
            "<b>Источник:</b> <code>{chat}</code>\n"
            "<b>Автор:</b> <code>{sender}</code>\n"
            "<b>Дата:</b> <code>{date}</code>\n"
            "<b>Просмотры:</b> <code>{views}</code>\n"
            "<b>Медиа:</b> <code>{media}</code>\n\n"
            "<b>Содержимое:</b>\n"
            "<blockquote>{text}</blockquote>"
        ),
        "ghost_usage": "<b>[!]</b> Использование: <code>.ghost &lt;секунды&gt; &lt;текст&gt;</code>",
        "ghost_sent": "<b>[~]</b> Самоуничтожение сообщения через {sec}с...",
        "pw_generated": (
            "<b>[+] Сгенерированный пароль</b>\n\n"
            "<b>Значение:</b> <code>{password}</code>\n"
            "<b>Длина:</b> <code>{length}</code> символов\n"
            "<b>Энтропия:</b> <code>{entropy:.1f}</code> бит"
        ),
    }

    @loader.command()
    @loader.tag(aliases=["curl", "untrack"])
    async def cleanurl(self, message: Message):
        """<url or reply> - Strip tracking parameters (utm, si, fbclid, etc.) from links"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        target_text = args
        if not target_text and reply:
            target_text = reply.raw_text or ""

        if not target_text:
            await utils.answer(message, self.strings("cleanurl_usage"))
            return

        urls = re.findall(r"https?://[^\s<>\"']+", target_text)
        if not urls:
            await utils.answer(message, self.strings("cleanurl_usage"))
            return

        cleaned_urls = []
        for raw_u in urls:
            unshortened = await unshorten_url(raw_u)
            cleaned = clean_url_params(unshortened)
            cleaned_urls.append(cleaned)

        if len(cleaned_urls) == 1:
            await utils.answer(
                message,
                self.strings("cleanurl_cleaned").format(
                    url=utils.escape_html(cleaned_urls[0])
                ),
            )
        else:
            links_text = "\n".join(
                f"• <code>{utils.escape_html(u)}</code>" for u in cleaned_urls
            )
            await utils.answer(
                message,
                self.strings("cleanurl_multi").format(
                    count=len(cleaned_urls),
                    links=links_text,
                ),
            )

    @loader.command()
    @loader.tag(aliases=["dewmark", "nowatermark", "stego"])
    async def unmark(self, message: Message):
        """[reply or text] - Scan and strip zero-width fingerprinting watermarks from text"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        source_text = args
        if not source_text and reply:
            source_text = reply.raw_text or ""

        if not source_text:
            await utils.answer(message, self.strings("unmark_usage"))
            return

        found_marks = []
        for idx, char in enumerate(source_text):
            code = ord(char)
            if code in ZERO_WIDTH_CHARS:
                found_marks.append((idx, code, ZERO_WIDTH_CHARS[code]))

        if not found_marks:
            await utils.answer(message, self.strings("unmark_clean"))
            return

        details_lines = []
        mark_counts = {}
        for _, code, name in found_marks:
            mark_counts[name] = mark_counts.get(name, 0) + 1

        for name, count in mark_counts.items():
            details_lines.append(f"• <code>{name}</code>: {count}x")

        clean_text = ZERO_WIDTH_RE.sub("", source_text)

        await utils.answer(
            message,
            self.strings("unmark_found").format(
                count=len(found_marks),
                details="\n".join(details_lines),
                clean_text=utils.escape_html(clean_text),
            ),
        )

    @loader.command()
    @loader.tag(aliases=["noexif", "cleanmedia", "anonymize"])
    async def strip(self, message: Message):
        """[reply to photo/video/file] - Purge EXIF, GPS, camera model and device metadata"""
        reply = await message.get_reply_message()
        if not reply or not (reply.photo or reply.video or reply.file):
            await utils.answer(message, self.strings("strip_usage"))
            return

        status_msg = await utils.answer(message, self.strings("strip_processing"))

        with tempfile.TemporaryDirectory() as tmp:
            src_file = os.path.join(tmp, "source_media")
            dl_path = await message.client.download_media(reply, file=src_file)
            if not dl_path or not os.path.exists(dl_path):
                await utils.answer(status_msg, self.strings("strip_failed"))
                return

            out_file = None
            is_image = False
            try:
                from PIL import Image

                with Image.open(dl_path) as img:
                    is_image = True
                    clean_img = Image.new(img.mode, img.size)
                    clean_img.paste(img)
                    out_file = os.path.join(tmp, "clean_image.jpg")
                    clean_img.save(out_file, "JPEG", quality=95)
            except Exception:
                is_image = False

            if not is_image:
                out_file = os.path.join(tmp, "clean_media" + os.path.splitext(dl_path)[1])
                ffmpeg_bin = "ffmpeg"
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    dl_path,
                    "-map_metadata",
                    "-1",
                    "-c",
                    "copy",
                    out_file,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.communicate()

            if out_file and os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                await message.client.send_file(
                    message.chat_id,
                    out_file,
                    caption=self.strings("strip_done"),
                    reply_to=reply.id,
                )
                await status_msg.delete()
            else:
                await utils.answer(status_msg, self.strings("strip_failed"))

    @loader.command()
    @loader.tag(aliases=["ghostread", "sneak"])
    async def peek(self, message: Message):
        """<t.me link or reply> - Inspect message contents without triggering read receipts"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        target_link = args
        target_msg = None

        if reply:
            target_msg = reply
        elif target_link:
            link_match = re.search(r"t\.me/(?:c/)?([^/]+)/(\d+)", target_link)
            if link_match:
                chat_part = link_match.group(1)
                msg_id = int(link_match.group(2))
                try:
                    if chat_part.isdigit():
                        peer = int("-100" + chat_part)
                    else:
                        peer = chat_part
                    target_msg = await message.client.get_messages(peer, ids=msg_id)
                except Exception as e:
                    await utils.answer(
                        message, self.strings("peek_error").format(utils.escape_html(str(e)))
                    )
                    return

        if not target_msg:
            await utils.answer(message, self.strings("peek_usage"))
            return

        chat_title = "Unknown"
        try:
            chat_entity = await target_msg.get_chat()
            chat_title = (
                getattr(chat_entity, "title", None)
                or getattr(chat_entity, "username", None)
                or str(target_msg.chat_id)
            )
        except Exception:
            chat_title = str(target_msg.chat_id)

        sender_name = "Anonymous"
        try:
            sender = await target_msg.get_sender()
            if sender:
                sender_name = (
                    getattr(sender, "first_name", "")
                    + " "
                    + (getattr(sender, "last_name", "") or "")
                ).strip() or getattr(sender, "title", None) or getattr(sender, "username", None) or str(sender.id)
        except Exception:
            sender_name = "Unknown"

        date_str = target_msg.date.strftime("%Y-%m-%d %H:%M:%S UTC") if target_msg.date else "Unknown"
        views = getattr(target_msg, "views", None)
        views_str = str(views) if views is not None else "None"

        media_str = "None"
        if target_msg.photo:
            media_str = "Photo"
        elif target_msg.video:
            media_str = "Video"
        elif target_msg.voice:
            media_str = "Voice Note"
        elif target_msg.audio:
            media_str = "Audio File"
        elif target_msg.document:
            media_str = f"Document ({getattr(target_msg.file, 'name', 'file')})"

        body_text = target_msg.raw_text or "No text"

        await utils.answer(
            message,
            self.strings("peek_info").format(
                chat=utils.escape_html(str(chat_title)),
                sender=utils.escape_html(str(sender_name)),
                date=date_str,
                views=views_str,
                media=media_str,
                text=utils.escape_html(body_text),
            ),
        )

    @loader.command()
    @loader.tag(aliases=["burn", "stealthmsg"])
    async def ghost(self, message: Message):
        """<seconds> <text> - Send self-destructing stealth message"""
        args = (utils.get_args_raw(message) or "").strip()
        if not args:
            await utils.answer(message, self.strings("ghost_usage"))
            return

        parts = args.split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit():
            await utils.answer(message, self.strings("ghost_usage"))
            return

        seconds = max(1, min(3600, int(parts[0])))
        content = parts[1]

        sent = await utils.answer(message, content)
        await asyncio.sleep(seconds)
        try:
            if sent:
                await sent.delete()
        except Exception:
            pass

    @loader.command()
    @loader.tag(aliases=["pw", "keygen"])
    async def passgen(self, message: Message):
        """[length] - Generate cryptographically secure password with entropy metrics"""
        args = (utils.get_args_raw(message) or "").strip()
        length = 16
        if args.isdigit():
            length = max(6, min(128, int(args)))

        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}<>,.?"
        chars = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()-_=+"),
        ]
        chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
        secrets.SystemRandom().shuffle(chars)
        pw = "".join(chars)

        entropy = length * math.log2(len(alphabet))

        await utils.answer(
            message,
            self.strings("pw_generated").format(
                password=pw,
                length=length,
                entropy=entropy,
            ),
        )
