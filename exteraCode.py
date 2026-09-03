# meta developer: @exterame

__version__ = (1, 0, 0)

import asyncio
import base64
import datetime
import difflib
import hashlib
import json
import logging
import math
import re
import sys
import time

from herokutl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

ALLOWED_MATH = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
ALLOWED_MATH.update(
    {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": pow,
        "sum": sum,
        "int": int,
        "float": float,
    }
)


def safe_b64_decode(data_str: str) -> str:
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str.encode("utf-8")).decode("utf-8", errors="replace")


@loader.tds
class exteraCode(loader.Module):
    """Developer, code execution, diff inspection and cryptographic utilities"""

    developer = "@exterame"

    strings = {
        "name": "exteraCode",
        "_cls_doc": "Developer, code execution, diff inspection and cryptographic utilities. Developer: @exterame",
        "run_usage": "<b>[!]</b> Usage: <code>.run [py/sh/node] &lt;code&gt;</code>",
        "running": "<b>[~]</b> Running code snippet...",
        "run_result": (
            "<b>[>] Execution Output ({lang}):</b>\n\n"
            "<b>Status:</b> <code>Exit {code}</code> | <b>Time:</b> <code>{duration:.3f}s</code>\n"
            "<pre><code class=\"language-{lang}\">{output}</code></pre>"
        ),
        "run_timeout": "<b>[!]</b> Execution timed out (limit: 10s).",
        "diff_usage": "<b>[!]</b> Reply to a message and specify new text to generate diff.",
        "diff_no_change": "<b>[+]</b> No differences found between texts.",
        "diff_result": (
            "<b>[>] Visual Diff:</b>\n\n"
            "<pre><code class=\"language-diff\">{diff}</code></pre>"
        ),
        "calc_usage": "<b>[!]</b> Usage: <code>.calc &lt;math expression&gt;</code>",
        "calc_result": (
            "<b>[>] Calculation:</b>\n\n"
            "<b>Expr:</b> <code>{expr}</code>\n"
            "<b>Result:</b> <code>{result}</code>"
        ),
        "calc_error": "<b>[!]</b> Calculation error: <code>{}</code>",
        "hash_usage": "<b>[!]</b> Provide text or reply to a message to calculate hashes.",
        "hash_result": (
            "<b>[>] Cryptographic Hashes:</b>\n\n"
            "<b>MD5:</b>\n<code>{md5}</code>\n\n"
            "<b>SHA-1:</b>\n<code>{sha1}</code>\n\n"
            "<b>SHA-256:</b>\n<code>{sha256}</code>\n\n"
            "<b>SHA-512:</b>\n<code>{sha512}</code>"
        ),
        "b64_usage": "<b>[!]</b> Usage: <code>.b64 [e/d] &lt;text or reply&gt;</code>",
        "b64_result": (
            "<b>[>] Base64 {mode}:</b>\n\n"
            "<code>{output}</code>"
        ),
        "b64_error": "<b>[!]</b> Failed to decode Base64 data.",
        "jwt_usage": "<b>[!]</b> Provide JWT token string or reply to message with token.",
        "jwt_invalid": "<b>[!]</b> Invalid JWT token format (expected 3 parts separated by dots).",
        "jwt_result": (
            "<b>[>] JWT Token Payload:</b>\n\n"
            "<b>Header:</b>\n<pre><code class=\"language-json\">{header}</code></pre>\n\n"
            "<b>Payload:</b>\n<pre><code class=\"language-json\">{payload}</code></pre>\n\n"
            "<b>Signature:</b> <code>{signature}</code>"
        ),
    }

    strings_ru = {
        "_cls_doc": "Инструменты разработчика: запуск кода, вычисление diff, криптографические хеши и декодер токенов. Разработчик: @exterame",
        "run_usage": "<b>[!]</b> Использование: <code>.run [py/sh/node] &lt;код&gt;</code>",
        "running": "<b>[~]</b> Выполнение кода...",
        "run_result": (
            "<b>[>] Результат выполнения ({lang}):</b>\n\n"
            "<b>Статус:</b> <code>Код {code}</code> | <b>Время:</b> <code>{duration:.3f}с</code>\n"
            "<pre><code class=\"language-{lang}\">{output}</code></pre>"
        ),
        "run_timeout": "<b>[!]</b> Время выполнения превышено (лимит: 10с).",
        "diff_usage": "<b>[!]</b> Ответьте на сообщение и укажите новый текст для генерации diff.",
        "diff_no_change": "<b>[+]</b> Различий между текстами не обнаружено.",
        "diff_result": (
            "<b>[>] Визуальный Diff:</b>\n\n"
            "<pre><code class=\"language-diff\">{diff}</code></pre>"
        ),
        "calc_usage": "<b>[!]</b> Использование: <code>.calc &lt;выражение&gt;</code>",
        "calc_result": (
            "<b>[>] Вычисление:</b>\n\n"
            "<b>Выражение:</b> <code>{expr}</code>\n"
            "<b>Результат:</b> <code>{result}</code>"
        ),
        "calc_error": "<b>[!]</b> Ошибка вычисления: <code>{}</code>",
        "hash_usage": "<b>[!]</b> Введите текст или ответьте на сообщение для расчета хешей.",
        "hash_result": (
            "<b>[>] Криптографические хеши:</b>\n\n"
            "<b>MD5:</b>\n<code>{md5}</code>\n\n"
            "<b>SHA-1:</b>\n<code>{sha1}</code>\n\n"
            "<b>SHA-256:</b>\n<code>{sha256}</code>\n\n"
            "<b>SHA-512:</b>\n<code>{sha512}</code>"
        ),
        "b64_usage": "<b>[!]</b> Использование: <code>.b64 [e/d] &lt;текст или ответ&gt;</code>",
        "b64_result": (
            "<b>[>] Base64 {mode}:</b>\n\n"
            "<code>{output}</code>"
        ),
        "b64_error": "<b>[!]</b> Ошибка декодирования Base64.",
        "jwt_usage": "<b>[!]</b> Укажите JWT токен или ответьте на сообщение с токеном.",
        "jwt_invalid": "<b>[!]</b> Некорректный формат JWT (ожидается 3 части через точку).",
        "jwt_result": (
            "<b>[>] JWT Payload токена:</b>\n\n"
            "<b>Заголовок:</b>\n<pre><code class=\"language-json\">{header}</code></pre>\n\n"
            "<b>Полезная нагрузка:</b>\n<pre><code class=\"language-json\">{payload}</code></pre>\n\n"
            "<b>Подпись:</b> <code>{signature}</code>"
        ),
    }

    @loader.command()
    @loader.tag(aliases=["exec", "runcode"])
    async def run(self, message: Message):
        """[py/sh/node] <code> - Execute code snippet in subprocess sandbox"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        lang = "py"
        code = args

        if args:
            parts = args.split(None, 1)
            first = parts[0].lower()
            if first in {"py", "python", "sh", "bash", "js", "node"}:
                lang = "py" if first in {"py", "python"} else ("sh" if first in {"sh", "bash"} else "node")
                code = parts[1] if len(parts) > 1 else ""

        if not code and reply:
            code = reply.raw_text or ""

        if not code:
            await utils.answer(message, self.strings("run_usage"))
            return

        status_msg = await utils.answer(message, self.strings("running"))

        if lang == "py":
            cmd = [sys.executable, "-c", code]
        elif lang == "sh":
            cmd = ["bash", "-c", code]
        else:
            cmd = ["node", "-e", code]

        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            duration = time.time() - start_time
            exit_code = proc.returncode

            out_text = stdout.decode("utf-8", errors="replace").strip()
            err_text = stderr.decode("utf-8", errors="replace").strip()

            combined = out_text
            if err_text:
                combined = (out_text + "\n" if out_text else "") + "[STDERR]:\n" + err_text

            if not combined:
                combined = "(Empty output)"

            if len(combined) > 3500:
                combined = combined[:3500] + "\n... (truncated)"

            await utils.answer(
                status_msg,
                self.strings("run_result").format(
                    lang=lang,
                    code=exit_code,
                    duration=duration,
                    output=utils.escape_html(combined),
                ),
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            await utils.answer(status_msg, self.strings("run_timeout"))
        except Exception as e:
            await utils.answer(status_msg, f"<b>[!] Execution failed:</b> <code>{utils.escape_html(str(e))}</code>")

    @loader.command()
    async def diff(self, message: Message):
        """[reply to message] <new text> - Generate unified visual diff"""
        reply = await message.get_reply_message()
        if not reply or not reply.raw_text:
            await utils.answer(message, self.strings("diff_usage"))
            return

        new_text = (utils.get_args_raw(message) or "").strip()
        if not new_text:
            await utils.answer(message, self.strings("diff_usage"))
            return

        old_lines = reply.raw_text.splitlines()
        new_lines = new_text.splitlines()

        diff_lines = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=2))
        if len(diff_lines) <= 2:
            await utils.answer(message, self.strings("diff_no_change"))
            return

        diff_content = "\n".join(diff_lines[2:])
        if len(diff_content) > 3500:
            diff_content = diff_content[:3500] + "\n... (truncated)"

        await utils.answer(
            message,
            self.strings("diff_result").format(diff=utils.escape_html(diff_content)),
        )

    @loader.command()
    async def calc(self, message: Message):
        """<math expression> - Evaluate math expression safely"""
        expr = (utils.get_args_raw(message) or "").strip()
        if not expr:
            await utils.answer(message, self.strings("calc_usage"))
            return

        sanitized = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
        if not re.match(r"^[0-9a-zA-Z_\s\+\-\*\/\%\(\)\.\,\*\*]+$", sanitized):
            await utils.answer(message, self.strings("calc_error").format("Forbidden characters in expression"))
            return

        try:
            res = eval(sanitized, {"__builtins__": {}}, ALLOWED_MATH)
            if isinstance(res, float) and res.is_integer():
                res = int(res)
            formatted = f"{res:,}".replace(",", " ") if isinstance(res, (int, float)) else str(res)
            await utils.answer(
                message,
                self.strings("calc_result").format(
                    expr=utils.escape_html(expr),
                    result=utils.escape_html(str(formatted)),
                ),
            )
        except Exception as e:
            await utils.answer(message, self.strings("calc_error").format(utils.escape_html(str(e))))

    @loader.command()
    async def hash(self, message: Message):
        """[text or reply] - Compute MD5, SHA-1, SHA-256 and SHA-512 hashes"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        target_text = args
        if not target_text and reply:
            target_text = reply.raw_text or ""

        if not target_text:
            await utils.answer(message, self.strings("hash_usage"))
            return

        raw_bytes = target_text.encode("utf-8")
        md5 = hashlib.md5(raw_bytes).hexdigest()
        sha1 = hashlib.sha1(raw_bytes).hexdigest()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        sha512 = hashlib.sha512(raw_bytes).hexdigest()

        await utils.answer(
            message,
            self.strings("hash_result").format(
                md5=md5,
                sha1=sha1,
                sha256=sha256,
                sha512=sha512,
            ),
        )

    @loader.command()
    async def b64(self, message: Message):
        """[e/d] <text or reply> - Encode or decode Base64 string"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        mode = "encode"
        payload = args

        if args:
            parts = args.split(None, 1)
            first = parts[0].lower()
            if first in {"e", "enc", "encode"}:
                mode = "encode"
                payload = parts[1] if len(parts) > 1 else ""
            elif first in {"d", "dec", "decode"}:
                mode = "decode"
                payload = parts[1] if len(parts) > 1 else ""

        if not payload and reply:
            payload = reply.raw_text or ""

        if not payload:
            await utils.answer(message, self.strings("b64_usage"))
            return

        try:
            if mode == "encode":
                res = base64.b64encode(payload.encode("utf-8")).decode("utf-8")
                label = "Encoded"
            else:
                res = safe_b64_decode(payload)
                label = "Decoded"

            await utils.answer(
                message,
                self.strings("b64_result").format(
                    mode=label,
                    output=utils.escape_html(res),
                ),
            )
        except Exception:
            await utils.answer(message, self.strings("b64_error"))

    @loader.command()
    async def jwt(self, message: Message):
        """<token or reply> - Inspect and decode JWT token payload"""
        args = (utils.get_args_raw(message) or "").strip()
        reply = await message.get_reply_message()

        token = args
        if not token and reply:
            token = reply.raw_text or ""

        if not token:
            await utils.answer(message, self.strings("jwt_usage"))
            return

        parts = token.strip().split(".")
        if len(parts) != 3:
            await utils.answer(message, self.strings("jwt_invalid"))
            return

        try:
            header_json = safe_b64_decode(parts[0])
            payload_json = safe_b64_decode(parts[1])

            header = json.loads(header_json)
            payload = json.loads(payload_json)

            if "exp" in payload and isinstance(payload["exp"], (int, float)):
                exp_dt = datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.timezone.utc)
                payload["_exp_readable"] = exp_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            if "iat" in payload and isinstance(payload["iat"], (int, float)):
                iat_dt = datetime.datetime.fromtimestamp(payload["iat"], tz=datetime.timezone.utc)
                payload["_iat_readable"] = iat_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            fmt_header = json.dumps(header, indent=2, ensure_ascii=False)
            fmt_payload = json.dumps(payload, indent=2, ensure_ascii=False)
            sig = parts[2][:16] + "..." if len(parts[2]) > 16 else parts[2]

            await utils.answer(
                message,
                self.strings("jwt_result").format(
                    header=utils.escape_html(fmt_header),
                    payload=utils.escape_html(fmt_payload),
                    signature=utils.escape_html(sig),
                ),
            )
        except Exception as e:
            await utils.answer(message, f"<b>[!] JWT Parse Error:</b> <code>{utils.escape_html(str(e))}</code>")
