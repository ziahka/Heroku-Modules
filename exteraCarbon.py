# meta developer: @exterame

__version__ = (1, 0, 0)

import asyncio
import io
import logging
import os
import re
from PIL import Image, ImageDraw, ImageFont
from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

TOKEN_COLORS = {
    "COMMENT": (108, 112, 134),
    "STRING": (166, 227, 161),
    "DECORATOR": (116, 199, 236),
    "KEYWORD": (203, 166, 247),
    "NUMBER": (250, 179, 135),
    "CALL": (137, 180, 250),
    "IDENT": (205, 214, 244),
    "OTHER": (147, 153, 178),
    "SPACE": (205, 214, 244),
}

LINE_TOKEN_RE = re.compile(
    r'(?P<COMMENT>#[^\n]*|//[^\n]*)'
    r'|(?P<STRING>\"\"\"[\s\S]*?\"\"\"|\'\'\'[\s\S]*?\'\'\'|\"[^\"\n]*\"|\'[^\'\n]*\'|[“\"][^”\"\n]*[”\"])'
    r'|(?P<DECORATOR>@[^\s\(\)\[\]\{\}]+)'
    r'|(?P<KEYWORD>\b(?:def|class|import|from|return|if|else|elif|for|while|async|await|try|except|finally|with|as|lambda|yield|pass|break|continue|const|let|var|function|True|False|None)\b)'
    r'|(?P<NUMBER>\b\d+(?:\.\d+)?\b|0x[0-9a-fA-F]+)'
    r'|(?P<CALL>\b\w+(?=\s*\())'
    r'|(?P<IDENT>\b\w+\b)'
    r'|(?P<SPACE>\s+)'
    r'|(?P<OTHER>.)'
)

SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/liberation-mono/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "LiberationMono-Regular.ttf",
    "DejaVuSansMono.ttf",
    "monospace",
]


def get_mono_font(size: int = 24):
    for f_path in SYSTEM_FONTS:
        try:
            return ImageFont.truetype(f_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_carbon_card(
    code_text: str,
    title: str = "code.py",
    show_lines: bool = True,
    theme: str = "catppuccin",
) -> bytes:
    bg_color = (24, 24, 37, 255)
    win_color = (30, 30, 46, 255)
    border_color = (69, 71, 90, 255)
    title_color = (166, 173, 200)
    gutter_color = (108, 112, 134)

    if theme == "amoled":
        bg_color = (0, 0, 0, 255)
        win_color = (14, 14, 14, 255)
        border_color = (40, 40, 40, 255)
    elif theme == "nord":
        bg_color = (46, 52, 64, 255)
        win_color = (59, 66, 82, 255)
        border_color = (76, 86, 106, 255)

    font = get_mono_font(24)
    line_h = 36

    lines = code_text.strip().splitlines()
    if not lines:
        lines = ["# Empty snippet"]

    temp_img = Image.new("RGB", (100, 100))
    temp_draw = ImageDraw.Draw(temp_img)

    max_line_px = 300
    for line in lines:
        w = temp_draw.textlength(line, font=font)
        if w > max_line_px:
            max_line_px = int(w)

    gutter_w = 64 if show_lines else 24
    code_w = max_line_px + 40
    code_h = len(lines) * line_h + 30

    window_w = gutter_w + code_w
    window_h = 60 + code_h

    pad = 40
    total_w = window_w + pad * 2
    total_h = window_h + pad * 2

    canvas = Image.new("RGBA", (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    wx, wy = pad, pad
    draw.rounded_rectangle(
        (wx, wy, wx + window_w, wy + window_h),
        radius=16,
        fill=win_color,
        outline=border_color,
        width=2,
    )

    draw.ellipse((wx + 20, wy + 20, wx + 34, wy + 34), fill=(243, 139, 168))
    draw.ellipse((wx + 42, wy + 20, wx + 56, wy + 34), fill=(249, 226, 175))
    draw.ellipse((wx + 64, wy + 20, wx + 78, wy + 34), fill=(166, 227, 161))

    title_w = temp_draw.textlength(title, font=font)
    title_x = wx + (window_w - title_w) // 2
    draw.text((title_x, wy + 16), title, fill=title_color, font=font)

    y = wy + 62
    for idx, line in enumerate(lines, 1):
        if show_lines:
            num_str = f"{idx:2}"
            draw.text((wx + 20, y), num_str, fill=gutter_color, font=font)

        cursor_x = wx + gutter_w + 10
        for m in LINE_TOKEN_RE.finditer(line):
            part = m.group()
            token_type = m.lastgroup
            color = TOKEN_COLORS.get(token_type, (205, 214, 244))
            draw.text((cursor_x, y), part, fill=color, font=font)
            cursor_x += temp_draw.textlength(part, font=font)

        y += line_h

    bio = io.BytesIO()
    bio.name = "carbon.png"
    canvas.save(bio, "PNG")
    bio.seek(0)
    return bio.getvalue()


@loader.tds
class exteraCarbon(loader.Module):
    """High-resolution Carbon-style code card generator with syntax highlighting"""

    developer = "@exterame"

    strings = {
        "name": "exteraCarbon",
        "_cls_doc": "High-resolution Carbon-style code card generator with syntax highlighting. Developer: @exterame",
        "usage": "<b>[!]</b> Provide code text or reply to a message containing code.",
        "rendering": "<b>[~]</b> Generating Carbon code card...",
        "caption": "<b>[>] Generated via exteraCarbon</b>",
        "error": "<b>[!]</b> Failed to render code card: <code>{}</code>",
    }

    strings_ru = {
        "_cls_doc": "Генератор красивых карточек с кодом в стиле Carbon с подсветкой синтаксиса. Разработчик: @exterame",
        "usage": "<b>[!]</b> Введите код или ответьте на сообщение с кодом.",
        "rendering": "<b>[~]</b> Генерация карточки с кодом...",
        "caption": "<b>[>] Сгенерировано через exteraCarbon</b>",
        "error": "<b>[!]</b> Не удалось создать карточку: <code>{}</code>",
    }

    @loader.command()
    @loader.tag(aliases=["carb", "codecard"])
    async def carbon(self, message: Message):
        """[title] [flags] <code> - Render high-resolution Carbon code card image"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        code_text = args
        title = "code.py"
        show_lines = True
        theme = "catppuccin"

        if "--nolines" in code_text:
            show_lines = False
            code_text = code_text.replace("--nolines", "").strip()

        if "--amoled" in code_text:
            theme = "amoled"
            code_text = code_text.replace("--amoled", "").strip()
        elif "--nord" in code_text:
            theme = "nord"
            code_text = code_text.replace("--nord", "").strip()

        title_match = re.search(r"(?:--title|-t)\s+([^\s]+)", code_text)
        if title_match:
            title = title_match.group(1)
            code_text = (code_text[:title_match.start()] + code_text[title_match.end():]).strip()

        if not code_text and reply:
            code_text = reply.raw_text or ""

        if not code_text:
            await utils.answer(message, self.strings("usage"))
            return

        if title == "code.py":
            first_line = code_text.splitlines()[0].strip()
            if first_line.startswith(("#", "//", "/*")) and len(first_line.split()) > 1:
                potential_title = first_line.lstrip("#/* ").strip()
                if "." in potential_title and len(potential_title) < 32:
                    title = potential_title

        status_msg = await utils.answer(message, self.strings("rendering"))
        loop = asyncio.get_event_loop()
        try:
            png_data = await loop.run_in_executor(
                None, render_carbon_card, code_text, title, show_lines, theme
            )
            bio = io.BytesIO(png_data)
            bio.name = "carbon.png"

            reply_id = reply.id if reply else None
            await message.client.send_file(
                message.chat_id,
                bio,
                caption=self.strings("caption"),
                reply_to=reply_id,
            )
            await status_msg.delete()
        except Exception as e:
            logger.exception("Failed to render carbon card")
            await utils.answer(status_msg, self.strings("error").format(utils.escape_html(str(e))))
