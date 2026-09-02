__version__ = (1, 0, 0)

import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
from urllib.parse import urlparse

import aiohttp
from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

PHOTO_URL_RE = re.compile(
    r"(?:--photo|photo:)\s+(https?://[^\s]+)",
    re.IGNORECASE,
)

BUTTON_RE = re.compile(r"\[(.*?)\](?:\((.*?)\))?")


def parse_buttons(text: str) -> tuple[str, list[list[dict]], str | None]:
    lines = text.strip().splitlines()
    rows = []
    message_lines = []
    photo_url = None
    parsing_buttons = False

    photo_match = PHOTO_URL_RE.search(text)
    if photo_match:
        photo_url = photo_match.group(1)
        text = PHOTO_URL_RE.sub("", text)
        lines = text.strip().splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not parsing_buttons:
                message_lines.append(line)
            continue

        raw_matches = BUTTON_RE.findall(stripped)
        is_btn_line = bool(
            raw_matches
            and any(
                url or any(sep in label for sep in [":", "close", "unload"])
                for label, url in raw_matches
            )
        )

        if is_btn_line:
            parsing_buttons = True
            row = []
            for btn_label, btn_url in raw_matches:
                parts = [p.strip() for p in btn_label.split(":")]
                label = parts[0]
                style = None
                emoji_id = None
                action = None
                action_data = None

                for p in parts[1:]:
                    low = p.lower()
                    if low in {"danger", "red"}:
                        style = "danger"
                    elif low in {"success", "green"}:
                        style = "success"
                    elif low in {"primary", "blue"}:
                        style = "primary"
                    elif p.isdigit():
                        emoji_id = p
                    elif low == "close":
                        action = "close"
                    elif low == "unload":
                        action = "unload"
                    elif low.startswith("alert"):
                        action = "alert"
                        alert_parts = btn_label.split(":alert", 1)
                        if len(alert_parts) > 1 and alert_parts[1].startswith(":"):
                            action_data = alert_parts[1][1:].strip()
                    elif low.startswith("copy"):
                        action = "copy"
                        copy_parts = btn_label.split(":copy", 1)
                        if len(copy_parts) > 1 and copy_parts[1].startswith(":"):
                            action_data = copy_parts[1][1:].strip()
                    elif low.startswith("switch"):
                        action = "switch"
                        switch_parts = btn_label.split(":switch", 1)
                        if len(switch_parts) > 1 and switch_parts[1].startswith(":"):
                            action_data = switch_parts[1][1:].strip()

                b = {"text": label}
                if style:
                    b["style"] = style
                if emoji_id:
                    b["emoji_id"] = emoji_id

                if btn_url:
                    b["url"] = btn_url
                elif action == "close":
                    b["action"] = "close"
                elif action == "unload":
                    b["action"] = "unload"
                elif action == "alert":
                    b["action"] = "answer"
                    b["message"] = action_data or "Alert"
                    b["show_alert"] = True
                elif action == "copy":
                    b["copy"] = action_data or ""
                elif action == "switch":
                    b["switch_inline_query_current_chat"] = (action_data or "") + " "

                row.append(b)

            if row:
                rows.append(row)
        else:
            if not parsing_buttons:
                message_lines.append(line)

    clean_text = "\n".join(message_lines).strip()
    return clean_text, rows, photo_url


async def upload_image(file_path: str) -> str | None:
    try:
        data = aiohttp.FormData()
        with open(file_path, "rb") as f:
            data.add_field("files[]", f.read(), filename="image.jpg", content_type="image/jpeg")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://uguu.se/upload", data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    return res["files"][0]["url"]
    except Exception as e:
        logger.warning("Image upload failed: %s", e)
    return None


@loader.tds
class SmartButtons(loader.Module):
    """Create and send messages with interactive buttons, colors, custom emojis and images."""

    developer = "@exterame"

    strings = {
        "name": "SmartButtons",
        "_cls_doc": "Create and send messages with interactive buttons, colors, custom emojis and images. Developer: @exterame",
        "no_args": "<b>[Error]</b> Please provide text and buttons. Use .btnhelp for instructions.",
        "no_inline": "<b>[Error]</b> Inline bot is required for buttons. Please set up inline bot in Heroku settings.",
        "uploading_image": "<b>[Uploading image...]</b>",
        "upload_failed": "<b>[Error]</b> Failed to upload image.",
        "help_text": (
            "<b>[SmartButtons Help]</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>.btn Message text\n"
            "[Button 1](https://t.me/link) [Button 2 :primary](https://t.me/link)\n"
            "[Red Button :danger](https://t.me/link)\n"
            "[Green Button :success :5431402435497181911](https://t.me/link)\n"
            "[Copy Text :copy:Text to copy]\n"
            "[Alert Popup :alert:Alert text]\n"
            "[Close :close]</code>\n\n"
            "<b>Button Colors:</b>\n"
            "• <code>:primary</code> or <code>:blue</code>\n"
            "• <code>:success</code> or <code>:green</code>\n"
            "• <code>:danger</code> or <code>:red</code>\n\n"
            "<b>Custom Emojis:</b>\n"
            "• In message: <code>&lt;tg-emoji emoji-id=\"5431402435497181911\"&gt;icon&lt;/tg-emoji&gt;</code>\n"
            "• In button icon: <code>[Text :5431402435497181911](url)</code>\n\n"
            "<b>Image:</b>\n"
            "Reply to any photo or use <code>--photo &lt;url&gt;</code>\n\n"
            "<b>Inline:</b>\n"
            "<code>@bot btn Text | [Button](url)</code>"
        ),
        "inline_title": "Interactive Buttons",
        "inline_desc": "Usage: btn Text | [Button](url)",
        "inline_help": "<b>[SmartButtons]</b> Format: <code>@bot btn Text | [Button](url)</code>",
    }

    strings_ru = {
        "_cls_doc": "Создание сообщений с интерактивными кнопками, цветами, кастомными эмодзи и изображениями.",
        "no_args": "<b>[Ошибка]</b> Укажите текст и кнопки. Инструкция: .btnhelp",
        "no_inline": "<b>[Ошибка]</b> Для работы кнопок требуется настроенный инлайн-бот в Heroku.",
        "uploading_image": "<b>[Загрузка изображения...]</b>",
        "upload_failed": "<b>[Ошибка]</b> Не удалось загрузить изображение.",
        "help_text": (
            "<b>[SmartButtons Справка]</b>\n\n"
            "<b>Использование:</b>\n"
            "<code>.btn Текст сообщения\n"
            "[Кнопка 1](https://t.me/link) [Кнопка 2 :primary](https://t.me/link)\n"
            "[Красная кнопка :danger](https://t.me/link)\n"
            "[Зеленая с эмодзи :success :5431402435497181911](https://t.me/link)\n"
            "[Скопировать :copy:Текст для буфера]\n"
            "[Всплывающее окно :alert:Текст алерта]\n"
            "[Закрыть :close]</code>\n\n"
            "<b>Цвета кнопок:</b>\n"
            "• <code>:primary</code> или <code>:blue</code> (синяя)\n"
            "• <code>:success</code> или <code>:green</code> (зеленая)\n"
            "• <code>:danger</code> или <code>:red</code> (красная)\n\n"
            "<b>Кастомные эмодзи:</b>\n"
            "• В тексте: <code>&lt;tg-emoji emoji-id=\"5431402435497181911\"&gt;иконка&lt;/tg-emoji&gt;</code>\n"
            "• В иконке кнопки: <code>[Текст :5431402435497181911](url)</code>\n\n"
            "<b>Изображение:</b>\n"
            "Ответьте на фото командой <code>.btn</code> или укажите <code>--photo &lt;url&gt;</code>\n\n"
            "<b>Инлайн режим:</b>\n"
            "<code>@bot btn Текст | [Кнопка](url)</code>"
        ),
        "inline_title": "Сообщение с кнопками",
        "inline_desc": "Формат: btn Текст | [Кнопка](url)",
        "inline_help": "<b>[SmartButtons]</b> Формат: <code>@bot btn Текст | [Кнопка](url)</code>",
    }

    @loader.command()
    @loader.tag(aliases=["button", "buttons", "ibtn"])
    async def btn(self, message: Message):
        """<text> [buttons] - Send message with custom colored buttons, emojis, and image"""
        if not hasattr(self, "inline") or (
            not getattr(self.inline, "init_complete", False)
            and not getattr(self.inline, "bot_username", None)
        ):
            await utils.answer(message, self.strings("no_inline"))
            return

        raw_text = utils.get_args_raw(message) or ""
        reply = await message.get_reply_message()

        if not raw_text and reply and reply.raw_text:
            raw_text = reply.raw_text

        if not raw_text:
            await utils.answer(message, self.strings("no_args"))
            return

        clean_text, rows, photo_url = parse_buttons(raw_text)
        if not clean_text and not rows:
            await utils.answer(message, self.strings("no_args"))
            return

        if not clean_text:
            clean_text = " "

        status_msg = None
        if not photo_url and reply and (reply.photo or (reply.file and reply.file.mime_type and reply.file.mime_type.startswith("image/"))):
            status_msg = await utils.answer(message, self.strings("uploading_image"))
            with tempfile.TemporaryDirectory() as tmp:
                in_img = os.path.join(tmp, "image.jpg")
                dl_file = await message.client.download_media(reply, file=in_img)
                if dl_file and os.path.exists(dl_file):
                    photo_url = await upload_image(dl_file)

            if not photo_url and status_msg:
                await utils.answer(status_msg, self.strings("upload_failed"))
                return

        target_message = status_msg or message
        try:
            res = await self.inline.form(
                text=clean_text,
                message=target_message,
                reply_markup=rows,
                photo=photo_url,
                silent=True,
            )
            if not res and status_msg:
                await status_msg.delete()
        except Exception as e:
            logger.exception("Failed to send smart buttons form")
            await utils.answer(target_message, f"<b>[Error]</b> {utils.escape_html(str(e))}")

    @loader.command()
    async def btnhelp(self, message: Message):
        """- Show syntax instructions and examples for SmartButtons"""
        await utils.answer(message, self.strings("help_text"))

    @loader.inline_handler()
    async def btn_inline_handler(self, query):
        """Generate interactive buttons via inline query"""
        raw = query.query.strip()
        if raw.lower().startswith("btn"):
            raw = raw[3:].strip()

        if not raw:
            return {
                "title": self.strings("inline_title"),
                "description": self.strings("inline_desc"),
                "message": self.strings("inline_help"),
            }

        raw = raw.replace(" | ", "\n").replace("|", "\n")
        clean_text, rows, photo_url = parse_buttons(raw)

        if not clean_text:
            clean_text = " "

        if photo_url:
            return {
                "title": clean_text[:40] or "Buttons with photo",
                "description": "Interactive photo post",
                "photo": photo_url,
                "caption": clean_text,
                "reply_markup": rows,
            }

        return {
            "title": clean_text[:40] or "Buttons post",
            "description": "Interactive message with buttons",
            "message": clean_text,
            "reply_markup": rows,
        }
