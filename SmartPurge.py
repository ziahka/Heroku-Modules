# meta developer: @exterame

__version__ = (1, 0, 0)

import asyncio
import contextlib
import logging

from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class SmartPurge(loader.Module):
    """Advanced chat purging, auto-disappearing messages and cleaner suite."""

    developer = "@exterame"

    strings = {
        "name": "SmartPurge",
        "_cls_doc": "Advanced chat purging, auto-disappearing messages and cleaner suite. Developer: @exterame",
        "purging": "<b>[Purging...]</b>",
        "purged": "<b>[Purged]</b> Deleted {} messages.",
        "purgeme_done": "<b>[Purged]</b> Deleted {} of your messages.",
        "no_reply": "<b>[Error]</b> Reply to a message to purge from.",
        "perm_error": "<b>[Error]</b> Insufficient permissions to delete messages.",
        "disappear_set": "<b>[Auto-Delete]</b> Enabled: {}s in this chat.",
        "disappear_off": "<b>[Auto-Delete]</b> Disabled in this chat.",
        "disappear_status": "<b>[Auto-Delete]</b> Current timer: {}s (0 to disable).",
        "invalid_args": "<b>[Error]</b> Invalid arguments.",
        "group_only": "<b>[Error]</b> This command is only available in groups.",
        "cleaning_ghosts": "<b>[Cleaning...]</b> Searching for deleted accounts.",
        "ghosts_cleaned": "<b>[Done]</b> Removed {} deleted accounts.",
        "first_msg": "<b>[First Message]</b> <a href='{}'>Go to message ID {}</a>",
    }

    strings_ru = {
        "_cls_doc": "Продвинутая очистка чатов, самоуничтожающиеся сообщения и удаление призраков. Разработчик: @exterame",
        "purging": "<b>[Очистка...]</b>",
        "purged": "<b>[Очищено]</b> Удалено {} сообщений.",
        "purgeme_done": "<b>[Очищено]</b> Удалено {} ваших сообщений.",
        "no_reply": "<b>[Ошибка]</b> Ответьте на сообщение, от которого нужно начать очистку.",
        "perm_error": "<b>[Ошибка]</b> Недостаточно прав для удаления сообщений.",
        "disappear_set": "<b>[Авто-удаление]</b> Включено: {}с в этом чате.",
        "disappear_off": "<b>[Авто-удаление]</b> Отключено в этом чате.",
        "disappear_status": "<b>[Авто-удаление]</b> Текущий таймер: {}с (0 для отключения).",
        "invalid_args": "<b>[Ошибка]</b> Неверные аргументы.",
        "group_only": "<b>[Ошибка]</b> Команда доступна только в группах.",
        "cleaning_ghosts": "<b>[Очистка...]</b> Поиск удаленных аккаунтов.",
        "ghosts_cleaned": "<b>[Готово]</b> Удалено {} удаленных аккаунтов.",
        "first_msg": "<b>[Первое сообщение]</b> <a href='{}'>Перейти к сообщению ID {}</a>",
    }

    async def client_ready(self):
        self._timers = self._db.get(self.strings["name"], "timers", {})

    @loader.watcher(only_messages=True, out=True)
    async def auto_disappear_watcher(self, message: Message):
        if not getattr(message, "out", False):
            return
        chat_id = str(utils.get_chat_id(message))
        timers = self._db.get(self.strings["name"], "timers", {})
        delay = timers.get(chat_id)
        if delay and isinstance(delay, int) and delay > 0:
            asyncio.ensure_future(self._delayed_delete(message, delay))

    async def _delayed_delete(self, message: Message, delay: int):
        await asyncio.sleep(delay)
        with contextlib.suppress(Exception):
            await message.delete()

    @loader.command()
    async def purge(self, message: Message):
        """[count] - Purge messages from replied message up to current, or last N messages"""
        chat_id = utils.get_chat_id(message)
        reply = await message.get_reply_message()
        raw_args = utils.get_args_raw(message) or ""

        limit = None
        if raw_args.strip().isdigit():
            limit = int(raw_args.strip())

        ids = []
        if reply:
            start_id = reply.id
            end_id = message.id
            if start_id > end_id:
                start_id, end_id = end_id, start_id
            async for m in message.client.iter_messages(chat_id, min_id=start_id - 1, max_id=end_id + 1):
                ids.append(m.id)
                if limit and len(ids) >= limit:
                    break
        elif limit:
            async for m in message.client.iter_messages(chat_id, limit=limit + 1):
                ids.append(m.id)
        else:
            await utils.answer(message, self.strings("no_reply"))
            return

        if not ids:
            return

        try:
            for chunk in [ids[i : i + 100] for i in range(0, len(ids), 100)]:
                await message.client.delete_messages(chat_id, chunk, revoke=True)
        except Exception:
            await utils.answer(message, self.strings("perm_error"))
            return

        status = await message.client.send_message(
            chat_id,
            self.strings("purged").format(len(ids)),
        )
        await asyncio.sleep(3)
        with contextlib.suppress(Exception):
            await status.delete()

    @loader.command()
    @loader.tag(aliases=["pme"])
    async def purgeme(self, message: Message):
        """[count] - Purge only your own messages in current chat (default 50)"""
        chat_id = utils.get_chat_id(message)
        raw_args = utils.get_args_raw(message) or ""
        limit = int(raw_args.strip()) if raw_args.strip().isdigit() else 50

        ids = []
        async for m in message.client.iter_messages(chat_id, from_user="me", limit=limit + 1):
            ids.append(m.id)

        if not ids:
            return

        try:
            for chunk in [ids[i : i + 100] for i in range(0, len(ids), 100)]:
                await message.client.delete_messages(chat_id, chunk, revoke=True)
        except Exception:
            await utils.answer(message, self.strings("perm_error"))
            return

        status = await message.client.send_message(
            chat_id,
            self.strings("purgeme_done").format(len(ids)),
        )
        await asyncio.sleep(3)
        with contextlib.suppress(Exception):
            await status.delete()

    @loader.command()
    @loader.tag(aliases=["del", "d"])
    async def delcmd(self, message: Message):
        """- Instantly delete replied message and this command"""
        reply = await message.get_reply_message()
        with contextlib.suppress(Exception):
            await message.delete()
        if reply:
            with contextlib.suppress(Exception):
                await reply.delete()

    @loader.command()
    @loader.tag(aliases=["autodel", "timer"])
    async def disappear(self, message: Message):
        """[seconds] - Set auto-delete timer for your messages in this chat (0 to disable)"""
        chat_id = str(utils.get_chat_id(message))
        raw_args = utils.get_args_raw(message) or ""

        timers = self._db.get(self.strings["name"], "timers", {})

        if not raw_args:
            cur = timers.get(chat_id, 0)
            await utils.answer(message, self.strings("disappear_status").format(cur))
            return

        if raw_args.lower() in {"0", "off", "disable", "stop"}:
            timers.pop(chat_id, None)
            self._db.set(self.strings["name"], "timers", timers)
            await utils.answer(message, self.strings("disappear_off"))
            return

        if raw_args.isdigit():
            val = int(raw_args)
            if val <= 0:
                timers.pop(chat_id, None)
                self._db.set(self.strings["name"], "timers", timers)
                await utils.answer(message, self.strings("disappear_off"))
            else:
                timers[chat_id] = val
                self._db.set(self.strings["name"], "timers", timers)
                await utils.answer(message, self.strings("disappear_set").format(val))
            return

        await utils.answer(message, self.strings("invalid_args"))

    @loader.command()
    @loader.tag(alias="kickdeleted")
    async def cleanghosts(self, message: Message):
        """- Kick all deleted accounts from current group"""
        chat_id = utils.get_chat_id(message)
        if message.is_private:
            await utils.answer(message, self.strings("group_only"))
            return

        status = await utils.answer(message, self.strings("cleaning_ghosts"))
        count = 0
        try:
            async for user in message.client.iter_participants(chat_id):
                if getattr(user, "deleted", False):
                    try:
                        await message.client.kick_participant(chat_id, user.id)
                        count += 1
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass
        except Exception:
            await utils.answer(status, self.strings("perm_error"))
            return

        await utils.answer(status, self.strings("ghosts_cleaned").format(count))

    @loader.command()
    async def firstmsg(self, message: Message):
        """- Find and link the first message in this chat"""
        chat_id = utils.get_chat_id(message)
        first_msgs = await message.client.get_messages(chat_id, limit=1, reverse=True)
        if not first_msgs:
            await utils.answer(message, self.strings("invalid_args"))
            return

        first = first_msgs[0]
        if getattr(message.chat, "username", None):
            link = f"https://t.me/{message.chat.username}/{first.id}"
        else:
            cid = str(chat_id).replace("-100", "").replace("-", "")
            link = f"https://t.me/c/{cid}/{first.id}"

        await utils.answer(message, self.strings("first_msg").format(link, first.id))
