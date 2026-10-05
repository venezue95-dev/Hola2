"""Adaptador de Pyrogram para el bot Upload ET.

Mantiene una interfaz pequeña compatible con las llamadas históricas de main.py,
pero recibe actualizaciones y archivos mediante Pyrogram real, no mediante un
parser manual de getUpdates.
"""
from __future__ import annotations

import os
import threading
import asyncio
from types import SimpleNamespace
from typing import Callable, Optional

from pyrogram import Client, enums, filters
from pyrogram.errors import MessageNotModified
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

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
        workdir = os.path.abspath(os.getenv("TELEGRAM_WORKDIR", "/app/data/telegram"))
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

    def onCallback(self, func: Callable):
        """Registra callbacks de botones inline y los entrega al bot con el mismo contexto de usuario."""
        self._callback_query = func
        self.app.add_handler(CallbackQueryHandler(self._on_callback))

    def _on_callback(self, _client, callback_query):
        callback = getattr(self, "_callback_query", None)
        if not callback:
            return
        try:
            callback(callback_query, self)
        except Exception as exc:
            print(f"Error en callback inline: {exc}")

    def _on_message(self, _client, message):
        if not self._callback:
            return
        update = UpdateCompat(message)
        self.this_thread = BotThread(targetfunc=self._callback, args=(update, self), update=update)
        update._thread = self.this_thread
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

    def sendMessage(self, chat_id=0, text="", parse_mode="", reply_markup=None):
        # Pyrogram 2 identifica el mensaje con `.id`; main.py usa `.message_id`.
        # MessageCompat expone ambos, así editMessageText/deleteMessage funcionan.
        sent = self.app.send_message(
            chat_id,
            text,
            parse_mode=self._parse_mode(parse_mode),
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return MessageCompat(sent)

    def editMessageText(self, message, text="", parse_mode="", reply_markup=None):
        if not message:
            return None
        message_id = getattr(message, "message_id", None) or message.id
        try:
            return self.app.edit_message_text(
                message.chat.id,
                message_id,
                text,
                parse_mode=self._parse_mode(parse_mode),
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except MessageNotModified:
            # El texto es idéntico al actual (pasa en las barras de progreso).
            return None
        except Exception as exc:
            # La edición es solo visual; no debe abortar una descarga o subida.
            print(f"Aviso Pyrogram editMessageText: {exc}")
            return None

    def answerCallbackQuery(self, callback_query, text=None, show_alert=False):
        try:
            return self.app.answer_callback_query(
                callback_query.id, text=text, show_alert=show_alert
            )
        except Exception as exc:
            print(f"Aviso answerCallbackQuery: {exc}")
            return None

    @staticmethod
    def callbackUpdate(callback_query, text):
        """Convierte un botón inline en una actualización mínima compatible con main.py."""
        msg = callback_query.message
        user = callback_query.from_user
        return SimpleNamespace(
            message=SimpleNamespace(
                sender=user,
                from_user=user,
                chat=msg.chat,
                message_id=msg.id,
                text=text,
                caption=None,
                _message=msg,
            )
        )

    def deleteMessage(self, chat_id, msg_id):
        return self.app.delete_messages(chat_id, msg_id)

    def sendFile(self, chat_id, file, type="document"):
        if type == "video":
            return self.app.send_video(chat_id, file)
        return self.app.send_document(chat_id, file)

    def downloadMessage(self, message, destname, progressfunc=None, args=None, expected_size=0, retries=3, cancel_check=None):
        """Descarga un archivo de Telegram y verifica que coincida con el tamaño anunciado."""
        last_error = None
        expected_size = int(expected_size or 0)

        for attempt in range(1, max(1, retries) + 1):
            try:
                if attempt > 1:
                    try:
                        if os.path.exists(destname):
                            os.remove(destname)
                    except OSError:
                        pass

                # Pyrogram's Client owns the asyncio loop created by app.run().
                # The bot processes messages in worker threads, so invoking the
                # sync download wrapper from those threads can leave the media
                # transfer on the wrong event loop and, in practice, return only
                # the first 1 MiB chunk. Schedule the complete stream on the
                # client's real loop instead.
                async def _stream_download():
                    current = 0
                    os.makedirs(os.path.dirname(os.path.abspath(destname)), exist_ok=True)
                    with open(destname, "wb") as output:
                        async for chunk in self.app.stream_media(message._message):
                            if cancel_check and cancel_check():
                                raise RuntimeError("Descarga cancelada por el usuario")
                            output.write(chunk)
                            current += len(chunk)
                            if progressfunc:
                                await self.app.loop.run_in_executor(
                                    None, progressfunc, destname, current, expected_size, 0, 0, args
                                )
                    return current

                future = asyncio.run_coroutine_threadsafe(_stream_download(), self.app.loop)
                received = future.result()
                path = destname
                if not path or not os.path.isfile(path):
                    raise IOError("Telegram no devolvió el archivo descargado")

                actual_size = os.path.getsize(path)
                if expected_size > 0 and actual_size != expected_size:
                    raise IOError(
                        f"Descarga incompleta: Telegram indicó {expected_size} bytes, "
                        f"pero se recibieron {actual_size} bytes"
                    )
                if actual_size <= 0:
                    raise IOError("El archivo descargado está vacío")
                return path
            except Exception as exc:
                last_error = exc
                if cancel_check and cancel_check():
                    print("Descarga directa Telegram cancelada por el usuario")
                    break
                print(f"Descarga directa Telegram: intento {attempt}/{retries} falló: {exc}")
                if attempt < retries:
                    import time
                    time.sleep(2)

        try:
            if os.path.exists(destname):
                os.remove(destname)
        except OSError:
            pass
        raise last_error or IOError("No se pudo descargar el archivo de Telegram")

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
