"""Adaptador de Pyrogram para el bot Upload ET.

Mantiene una interfaz pequeña compatible con las llamadas históricas de main.py,
pero recibe actualizaciones y archivos mediante Pyrogram real, no mediante un
parser manual de getUpdates.
"""
from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from typing import Callable, Optional

from pyrogram import Client, enums, filters
from pyrogram.handlers import MessageHandler

from thread_context import BotThread
from bot_utils import get_url_file_name, req_file_size, sizeof_fmt, get_file_size, createID, nice_time


inlineQueryResultArticle = None


class MessageCompat:
    """Expone sender/text sin romper los accesos existentes de main.py."""

    def __init__(self, message):
        self._message = message
        self.chat = message.chat
        self.message_id = message.id
        self.from_user = message.from_user
        self.sender = message.from_user
        self.text = message.text or message.caption or ""

    def __getattr__(self, name):
        return getattr(self._message, name)


class UpdateCompat:
    def __init__(self, message):
        self.message = MessageCompat(message)


class PyrogramBotClient:
    def __init__(self, token: str):
        api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        if not api_id_raw or not api_hash:
            raise RuntimeError(
                "Faltan TELEGRAM_API_ID y TELEGRAM_API_HASH. "
                "Obtén ambos valores en my.telegram.org y guárdalos en .env."
            )
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise RuntimeError("TELEGRAM_API_ID debe ser un número entero.") from exc
        if not token:
            raise RuntimeError("Falta BOT_TOKEN en .env.")

        self.this_thread: Optional[BotThread] = None
        self._callback: Optional[Callable] = None
        # Pyrogram no crea la carpeta de la sesión; sin ella SQLite falla con
        # "unable to open database file".
        workdir = os.path.abspath(os.getenv("TELEGRAM_WORKDIR", ".telegram_session"))
        os.makedirs(workdir, exist_ok=True)
        self.app = Client(
            os.getenv("TELEGRAM_SESSION_NAME", "upload_et_bot"),
            api_id=api_id,
            api_hash=api_hash,
            bot_token=token,
            workdir=workdir,
        )

    def onMessage(self, func: Callable):
        self._callback = func
        self.app.add_handler(MessageHandler(self._on_message, filters.all))

    def _on_message(self, _client, message):
        if not self._callback:
            return
        update = UpdateCompat(message)
        self.this_thread = BotThread(targetfunc=self._callback, args=(update, self), update=update)
        self.this_thread.start()

    def run(self):
        self.app.run()

    @staticmethod
    def _parse_mode(parse_mode):
        if str(parse_mode).lower() in ("html", "parsemode.html"):
            return enums.ParseMode.HTML
        if str(parse_mode).lower() in ("markdown", "markdownv2"):
            return enums.ParseMode.MARKDOWN
        return enums.ParseMode.DISABLED

    def sendMessage(self, chat_id=0, text="", parse_mode=""):
        return self.app.send_message(
            chat_id,
            text,
            parse_mode=self._parse_mode(parse_mode),
            disable_web_page_preview=True,
        )

    def editMessageText(self, message, text="", parse_mode=""):
        if not message:
            return None
        return self.app.edit_message_text(
            message.chat.id,
            message.message_id,
            text,
            parse_mode=self._parse_mode(parse_mode),
            disable_web_page_preview=True,
        )

    def deleteMessage(self, chat_id, msg_id):
        return self.app.delete_messages(chat_id, msg_id)

    def sendFile(self, chat_id, file, type="document"):
        if type == "video":
            return self.app.send_video(chat_id, file)
        return self.app.send_document(chat_id, file)

    def downloadMessage(self, message, destname, progressfunc=None, args=None):
        """Descarga un documento/video/audio de Telegram al disco local."""
        last_report = {"time": 0.0}

        def progress(current, total, _):
            if progressfunc:
                progressfunc(destname, current, total, 0, 0, args)

        result = message._message.download(file_name=destname, progress=progress)
        return result or destname

    def getFile(self, file_id):
        return self.app.get_file(file_id)

    def on(self, _name, _func):
        # Se conserva por compatibilidad; el bot actual usa onMessage.
        return None

    def onInline(self, _func):
        return None

    def startNewThread(self, targetfunc=None, args=(), update=None):
        self.this_thread = BotThread(targetfunc=targetfunc, args=args, update=update)
        self.this_thread.start()
        return self.this_thread

    def stop(self):
        self.app.stop()
