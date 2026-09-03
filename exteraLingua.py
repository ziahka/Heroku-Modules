# meta developer: @exterame

__version__ = (1, 0, 0)

import asyncio
import html
import json
import logging
import re
import urllib.parse
import urllib.request

from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

COMMON_LANGS = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "uk": "Ukrainian",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "fi": "Finnish",
    "cs": "Czech",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "fa": "Persian",
    "uz": "Uzbek",
    "kk": "Kazakh",
}


def fetch_google_mobile(text: str, sl: str, tl: str) -> str:
    url = f"https://translate.google.com/m?sl={sl}&tl={tl}&q={urllib.parse.quote(text)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 Chrome/119.0.0.0"
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        m = re.search(r"class=\"result-container\">(.*?)</div>", body, re.DOTALL)
        if m:
            return html.unescape(m.group(1).strip())
    return ""


def fetch_mymemory(text: str, sl: str, tl: str) -> str:
    source = "en" if sl == "auto" else sl
    url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair={source}|{tl}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return data.get("responseData", {}).get("translatedText", "")


async def async_translate(text: str, tl: str = "ru", sl: str = "auto") -> str:
    loop = asyncio.get_event_loop()
    try:
        res = await loop.run_in_executor(None, fetch_google_mobile, text, sl, tl)
        if res and res != text:
            return res
    except Exception:
        pass

    try:
        res = await loop.run_in_executor(None, fetch_mymemory, text, sl, tl)
        if res and res != text:
            return res
    except Exception:
        pass

    return text


@loader.tds
class exteraLingua(loader.Module):
    """Seamless polyglot translator and bidirectional auto-translate watcher"""

    developer = "@exterame"

    strings = {
        "name": "exteraLingua",
        "_cls_doc": "Seamless polyglot translator and bidirectional auto-translate watcher. Developer: @exterame",
        "no_text": "<b>[!]</b> Provide text or reply to a message to translate.",
        "translating": "<b>[~]</b> Translating text...",
        "translated": (
            "<b>[+] Translation ({lang}):</b>\n"
            "<blockquote>{text}</blockquote>"
        ),
        "autotr_enabled": (
            "<b>[+] Auto-translate enabled for this chat.</b>\n"
            "Target language: <code>{lang}</code>\n"
            "Outgoing messages will be translated automatically."
        ),
        "autotr_disabled": "<b>[-] Auto-translate disabled for this chat.</b>",
        "autotr_status": (
            "<b>[>] Auto-Translate Status:</b>\n\n"
            "Active chats ({count}):\n"
            "{chats}"
        ),
        "autotr_no_chats": "<b>[!]</b> No chats have auto-translate enabled.",
        "langs_list": (
            "<b>[>] Supported Language Codes:</b>\n\n"
            "{list}\n\n"
            "Usage: <code>.lingua en Hello</code> or <code>.autotr de</code>"
        ),
    }

    strings_ru = {
        "_cls_doc": "Умный переводчик и автоматический двусторонний перевод переписок в реальном времени. Разработчик: @exterame",
        "no_text": "<b>[!]</b> Введите текст или ответьте на сообщение для перевода.",
        "translating": "<b>[~]</b> Перевод текста...",
        "translated": (
            "<b>[+] Перевод ({lang}):</b>\n"
            "<blockquote>{text}</blockquote>"
        ),
        "autotr_enabled": (
            "<b>[+] Автоперевод включен для этого чата.</b>\n"
            "Язык перевода: <code>{lang}</code>\n"
            "Исходящие сообщения будут переводиться автоматически."
        ),
        "autotr_disabled": "<b>[-] Автоперевод выключен для этого чата.</b>",
        "autotr_status": (
            "<b>[>] Активные чаты с автопереводом:</b>\n\n"
            "Всего ({count}):\n"
            "{chats}"
        ),
        "autotr_no_chats": "<b>[!]</b> Нет активных чатов с автопереводом.",
        "langs_list": (
            "<b>[>] Популярные коды языков:</b>\n\n"
            "{list}\n\n"
            "Использование: <code>.lingua en Привет</code> или <code>.autotr de</code>"
        ),
    }

    async def client_ready(self, client, db):
        self._db = db
        self._client = client

    @loader.command()
    @loader.tag(aliases=["tl", "trans", "extr"])
    async def lingua(self, message: Message):
        """[lang] [text or reply] - Translate text to target language"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        target_lang = "ru"
        text_to_translate = ""

        if args:
            parts = args.split(None, 1)
            first = parts[0].lower()
            if first in COMMON_LANGS or len(first) == 2:
                target_lang = first
                text_to_translate = parts[1] if len(parts) > 1 else ""
            else:
                text_to_translate = args

        if not text_to_translate and reply:
            text_to_translate = reply.raw_text or ""

        if not text_to_translate:
            await utils.answer(message, self.strings("no_text"))
            return

        status_msg = await utils.answer(message, self.strings("translating"))
        translated = await async_translate(text_to_translate, tl=target_lang)

        await utils.answer(
            status_msg,
            self.strings("translated").format(
                lang=target_lang.upper(),
                text=utils.escape_html(translated),
            ),
        )

    @loader.command()
    @loader.tag(aliases=["atr"])
    async def autotr(self, message: Message):
        """[lang] - Toggle automatic outgoing translation in current chat"""
        args = (utils.get_args_raw(message) or "").strip().lower()
        chat_id = utils.get_chat_id(message)
        active_chats = self._db.get(self.strings("name"), "auto_chats", {})

        str_chat_id = str(chat_id)
        if str_chat_id in active_chats and not args:
            del active_chats[str_chat_id]
            self._db.set(self.strings("name"), "auto_chats", active_chats)
            await utils.answer(message, self.strings("autotr_disabled"))
            return

        target_lang = args if (args in COMMON_LANGS or len(args) == 2) else "en"
        active_chats[str_chat_id] = target_lang
        self._db.set(self.strings("name"), "auto_chats", active_chats)

        await utils.answer(
            message,
            self.strings("autotr_enabled").format(lang=target_lang.upper()),
        )

    @loader.command()
    async def trchats(self, message: Message):
        """- Show all chats where auto-translate is enabled"""
        active_chats = self._db.get(self.strings("name"), "auto_chats", {})
        if not active_chats:
            await utils.answer(message, self.strings("autotr_no_chats"))
            return

        lines = []
        for cid, lang in active_chats.items():
            lines.append(f"• <code>{cid}</code>: <b>{lang.upper()}</b>")

        await utils.answer(
            message,
            self.strings("autotr_status").format(
                count=len(active_chats),
                chats="\n".join(lines),
            ),
        )

    @loader.command()
    async def trlangs(self, message: Message):
        """- Show popular language codes for translation"""
        lines = [f"• <code>{code}</code> — {name}" for code, name in sorted(COMMON_LANGS.items())]
        await utils.answer(
            message,
            self.strings("langs_list").format(list="\n".join(lines)),
        )

    @loader.watcher(out=True, only_messages=True)
    async def auto_translate_watcher(self, message: Message):
        if not message.raw_text or message.raw_text.startswith("."):
            return

        active_chats = self._db.get(self.strings("name"), "auto_chats", {})
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in active_chats:
            return

        target_lang = active_chats[chat_id]
        original_text = message.raw_text

        translated = await async_translate(original_text, tl=target_lang)
        if translated and translated != original_text:
            try:
                await message.edit(translated)
            except Exception:
                pass
