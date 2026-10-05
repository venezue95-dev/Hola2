from bot_utils import sizeof_fmt,get_file_size,createID,nice_time
from pyrogram_client import PyrogramBotClient
from MoodleClient import MoodleClient, StopUploadException
from JDatabase import JsonDatabase
import os
import infos
import xdlink
import datetime
import time
import NexCloudClient
from pydownloader.downloader import Downloader
from ProxyCloud import ProxyCloud
import ProxyCloud
from urllib.parse import unquote
import requests
import S5Crypto
import traceback
import pytz
import threading
import json
import collections
import re
import html
from dotenv import load_dotenv

load_dotenv()

# ==============================
# CONFIGURACIÓN DE LÍMITES DIARIOS
# ==============================
DAILY_LIMIT_BYTES = 16 * 1024 * 1024 * 1024  # 16 GB por defecto
CHUNK_SIZE_MB = max(1, int(os.getenv("CHUNK_SIZE_MB", "20")))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))

MAINTENANCE_MODE = False
BANNED_USERS = set()
REMOVED_USERS = set()
ACTIVE_PROCESSES = {}
ACTIVE_STATUS_CHECKS = set()
CHANGING_CLOUD_USERS = set()
USER_CLOUD_OVERRIDES = {}

try:
    CUBA_TZ = pytz.timezone('America/Havana')
except:
    CUBA_TZ = None

USER_EVIDENCE_MARKER = " "

AVAILABLE_CLOUDS = [
    {
        "cloudtype": "moodle",
        "moodle_host": "https://moodle.instec.cu/",
        "moodle_repo_id": 3,
        "moodle_user": "kevin.cruz",
        "moodle_password": os.getenv("MOODLE_PASSWORD_INSTEC", ""),
        "zips": 1023,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://aula.uclv.edu.cu/",
        "moodle_repo_id": 5,
        "moodle_user": "lircarrasco",
        "moodle_password": os.getenv("MOODLE_PASSWORD_UCLV", ""),
        "zips": 79,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://cursos.ucf.edu.cu/",
        "moodle_repo_id": 4,
        "moodle_user": "julianrene",
        "moodle_password": os.getenv("MOODLE_PASSWORD_UCF", ""),
        "zips": 4,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://cursos.fundacion.uh.cu/",
        "moodle_repo_id": 5,
        "moodle_user": "Claudia.btabares@estudiantes.instec.uh.cu",
        "moodle_password": os.getenv("MOODLE_PASSWORD_UH", ""),
        "zips": 11,
        "uploadtype": "draft",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://eva.umcc.cu/posgrado/",
        "moodle_repo_id": 5,
        "moodle_user": "daniela.martinez",
        "moodle_password": os.getenv("MOODLE_PASSWORD_UMCC_POSGRADO", ""),
        "zips": 99,
        "uploadtype": "draft",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://eva.umcc.cu/pregrado/",
        "moodle_repo_id": 5,
        "moodle_user": "daniela.martinez",
        "moodle_password": os.getenv("MOODLE_PASSWORD_UMCC_PREGRADO", ""),
        "zips": 19,
        "uploadtype": "draft",
        "proxy": "",
        "tokenize": 0
    },
    {
        "cloudtype": "moodle",
        "moodle_host": "https://uvp.ult.edu.cu/",
        "moodle_repo_id": 5,
        "moodle_user": "ariagnaav",
        "moodle_password": os.getenv("MOODLE_PASSWORD_ULT", ""),
        "zips": 99,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    }
]

PRE_CONFIGURATED_USERS = {
    "Thali355,Eliel_21,Kev_inn10,Loe_son": AVAILABLE_CLOUDS[0],
    "thu,hola1": AVAILABLE_CLOUDS[1],
    "VanNeiFertio,XD,SchnauzerMinnie": AVAILABLE_CLOUDS[2],
    "hola,usuario2": AVAILABLE_CLOUDS[3],
    "gatitoo_miauu,usuario_nuevo2": AVAILABLE_CLOUDS[4],
    "Satoru_2115,usuario_nuevo4": AVAILABLE_CLOUDS[5],
    "usuario1,usuario2,alejandrorosell,xanderpley,Hugo_Marrero": AVAILABLE_CLOUDS[6]
}

def get_user_info(username):
    if not username:
        return AVAILABLE_CLOUDS[0].copy()
    uname = username.lower()
    if uname in USER_CLOUD_OVERRIDES:
        return USER_CLOUD_OVERRIDES[uname].copy()
    
    for user_group, config in PRE_CONFIGURATED_USERS.items():
        users = [u.strip().lower() for u in user_group.split(',')]
        if uname in users:
            return config.copy()
            
    if uname == ADMIN_USERNAME.lower():
        return AVAILABLE_CLOUDS[0].copy()
        
    return AVAILABLE_CLOUDS[0].copy()

# ==============================
# SISTEMA DE CACHÉ PARA OPTIMIZACIÓN
# ==============================

class CloudCache:
    """Sistema de caché para evitar refrescos innecesarios"""
    def __init__(self, ttl_seconds=30):
        self.cache = {}
        self.ttl = ttl_seconds
        self.last_refresh = {}
        self.last_full_refresh = None
    
    def should_refresh(self, cloud_name=None):
        if cloud_name is None:
            if self.last_full_refresh is None:
                return True
            elapsed = (datetime.datetime.now() - self.last_full_refresh).total_seconds()
            return elapsed > self.ttl
        
        if cloud_name not in self.last_refresh:
            return True
        elapsed = (datetime.datetime.now() - self.last_refresh[cloud_name]).total_seconds()
        return elapsed > self.ttl
    
    def update_cache(self, cloud_name, data):
        self.cache[cloud_name] = data
        self.last_refresh[cloud_name] = datetime.datetime.now()
    
    def update_full_cache(self, data):
        self.cache = data.copy()
        self.last_full_refresh = datetime.datetime.now()
    
    def get_cache(self, cloud_name):
        return self.cache.get(cloud_name)
    
    def clear_cache(self):
        self.cache = {}
        self.last_refresh = {}
        self.last_full_refresh = None

cloud_cache = CloudCache(ttl_seconds=30)

def get_cuba_time():
    if CUBA_TZ:
        cuba_time = datetime.datetime.now(CUBA_TZ)
    else:
        cuba_time = datetime.datetime.now()
    return cuba_time

def format_cuba_date(dt=None):
    if dt is None:
        dt = get_cuba_time()
    return dt.strftime("%d/%m/%y")

def format_cuba_datetime(dt=None):
    if dt is None:
        dt = get_cuba_time()
    formatted_date = dt.strftime("%d/%m/%y")
    hour = str(int(dt.strftime("%I")))
    minute_ampm = dt.strftime("%M %p")
    return f"{formatted_date} {hour}:{minute_ampm}"

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    
    val = size_bytes / 1024.0
    if val < 1024:
        formatted = f"{val:.1f}"
        if formatted.endswith('.0'):
            formatted = formatted[:-2]
        return f"{formatted} KB"
    
    val /= 1024.0
    if val < 1024:
        formatted = f"{val:.1f}"
        if formatted.endswith('.0'):
            formatted = formatted[:-2]
        return f"{formatted} MB"
    
    val /= 1024.0
    if val < 1024:
        formatted = f"{val:.1f}"
        if formatted.endswith('.0'):
            formatted = formatted[:-2]
        return f"{formatted} GB"
    
    val /= 1024.0
    formatted = f"{val:.1f}"
    if formatted.endswith('.0'):
        formatted = formatted[:-2]
    return f"{formatted} TB"

# ==============================
# FUNCIONES PARA REACCIONES Y STICKERS
# ==============================
def send_reaction(chat_id, message_id, emoji="⚡"):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": json.dumps([{"type": "emoji", "emoji": emoji}])
        }
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Error al enviar reacción: {e}")

def send_sticker(chat_id, sticker_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendSticker"
        payload = {
            "chat_id": chat_id,
            "sticker": sticker_id
        }
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Error al enviar sticker: {e}")

# ==============================
# SISTEMA DE ESTADÍSTICAS EN MEMORIA Y CONTROL DIARIO
# ==============================

class MemoryStats:
    def __init__(self):
        self.reset_stats()
    
    def reset_stats(self):
        self.stats = {
            'total_uploads': 0,
            'total_deletes': 0,
            'total_size_uploaded': 0
        }
        self.user_stats = {}
        self.upload_logs = []
        self.delete_logs = []
    
    def check_and_update_daily_reset(self, username):
        current_date = format_cuba_date()
        if username in self.user_stats:
            if self.user_stats[username].get('last_date') != current_date:
                self.user_stats[username]['daily_size'] = 0
                self.user_stats[username]['last_date'] = current_date
        else:
            self.user_stats[username] = {
                'uploads': 0,
                'deletes': 0,
                'total_size': 0,
                'daily_size': 0,
                'last_date': current_date,
                'last_activity': format_cuba_datetime()
            }
    
    def log_upload(self, username, filename, file_size, moodle_host):
        try:
            file_size = int(file_size)
        except:
            file_size = 0
        
        self.check_and_update_daily_reset(username)
        
        self.stats['total_uploads'] += 1
        self.stats['total_size_uploaded'] += file_size
        
        self.user_stats[username]['uploads'] += 1
        self.user_stats[username]['total_size'] += file_size
        self.user_stats[username]['daily_size'] += file_size
        self.user_stats[username]['last_activity'] = format_cuba_datetime()
        
        log_entry = {
            'timestamp': format_cuba_datetime(),
            'username': username,
            'filename': filename,
            'file_size_bytes': file_size,
            'file_size_formatted': format_file_size(file_size),
            'moodle_host': moodle_host
        }
        self.upload_logs.append(log_entry)
        
        if len(self.upload_logs) > 300:
            self.upload_logs.pop(0)
        
        return True
    
    def log_delete(self, username, filename, evidence_name, moodle_host):
        self.stats['total_deletes'] += 1
        
        if username not in self.user_stats:
            current_date = format_cuba_date()
            self.user_stats[username] = {
                'uploads': 0,
                'deletes': 0,
                'total_size': 0,
                'daily_size': 0,
                'last_date': current_date,
                'last_activity': format_cuba_datetime()
            }
        
        self.user_stats[username]['deletes'] += 1
        self.user_stats[username]['last_activity'] = format_cuba_datetime()
        
        log_entry = {
            'timestamp': format_cuba_datetime(),
            'username': username,
            'filename': filename,
            'evidence_name': evidence_name,
            'moodle_host': moodle_host,
            'type': 'delete'
        }
        self.delete_logs.append(log_entry)
        
        if len(self.delete_logs) > 300:
            self.delete_logs.pop(0)
        
        return True
    
    def log_delete_all(self, username, deleted_evidences, deleted_files, moodle_host):
        self.stats['total_deletes'] += deleted_files
        
        if username not in self.user_stats:
            current_date = format_cuba_date()
            self.user_stats[username] = {
                'uploads': 0,
                'deletes': 0,
                'total_size': 0,
                'daily_size': 0,
                'last_date': current_date,
                'last_activity': format_cuba_datetime()
            }
        
        self.user_stats[username]['deletes'] += deleted_files
        self.user_stats[username]['last_activity'] = format_cuba_datetime()
        
        log_entry = {
            'timestamp': format_cuba_datetime(),
            'username': username,
            'action': 'delete_all',
            'deleted_evidences': deleted_evidences,
            'deleted_files': deleted_files,
            'moodle_host': moodle_host,
            'type': 'delete_all'
        }
        self.delete_logs.append(log_entry)
        
        if len(self.delete_logs) > 300:
            self.delete_logs.pop(0)
        
        return True
    
    def get_user_stats(self, username):
        self.check_and_update_daily_reset(username)
        if username in self.user_stats:
            return self.user_stats[username]
        return None
    
    def get_all_stats(self):
        return self.stats
    
    def get_all_users(self):
        return self.user_stats
    
    def get_recent_uploads(self, limit=10):
        return self.upload_logs[-limit:][::-1] if self.upload_logs else []
    
    def get_recent_deletes(self, limit=10):
        return self.delete_logs[-limit:][::-1] if self.delete_logs else []
    
    def has_any_data(self):
        return len(self.upload_logs) > 0 or len(self.delete_logs) > 0
    
    def clear_all_data(self):
        self.reset_stats()
        return "<b>✅ Todos los datos han sido eliminados</b>"

memory_stats = MemoryStats()

# ==============================
# SISTEMA DE COLAS POR USUARIO
# ==============================

class QueuedTask:
    def __init__(self, task_id, username, url, chat_id, filename="Desconocido"):
        self.task_id = task_id
        self.username = username
        self.url = url
        self.chat_id = chat_id
        self.filename = filename
        self.added_at = get_cuba_time()
        self.status = 'esperando'  # esperando | procesando
        self.thread_ctx = None

class QueueThreadContext:
    def __init__(self, task_id):
        self.id = task_id
        self._store = {}
    def store(self, key, value):
        self._store[key] = value
    def getStore(self, key):
        return self._store.get(key)

class _FakeSender:
    def __init__(self, username):
        self.username = username

class _FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id

class _FakeMessage:
    def __init__(self, username, chat_id):
        self.sender = _FakeSender(username)
        self.chat = _FakeChat(chat_id)

class _FakeUpdate:
    def __init__(self, username, chat_id):
        self.message = _FakeMessage(username, chat_id)

class QueueManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = {}
        self.pending = {}

    def _get_deque(self, username):
        if username not in self.pending:
            self.pending[username] = collections.deque()
        return self.pending[username]

    def submit(self, username, url, chat_id, task_id, filename="Desconocido"):
        with self.lock:
            task = QueuedTask(task_id, username, url, chat_id, filename)
            if self.active.get(username) is None:
                task.status = 'procesando'
                self.active[username] = task
                return task, True, 0
            else:
                dq = self._get_deque(username)
                dq.append(task)
                return task, False, len(dq)

    def find_task(self, task_id):
        with self.lock:
            for uname, t in self.active.items():
                if t and t.task_id == task_id:
                    return uname, t, 'active'
            for uname, dq in self.pending.items():
                for t in dq:
                    if t.task_id == task_id:
                        return uname, t, 'pending'
            return None, None, None

    def cancel(self, username, task_id):
        with self.lock:
            dq = self.pending.get(username, collections.deque())
            for t in list(dq):
                if t.task_id == task_id:
                    dq.remove(t)
                    return 'pending'
            active_task = self.active.get(username)
            if active_task and active_task.task_id == task_id:
                if active_task.thread_ctx:
                    active_task.thread_ctx.store('stop', True)
                return 'active'
        return None

    def advance(self, username):
        with self.lock:
            self.active[username] = None
            dq = self.pending.get(username)
            if dq and len(dq) > 0:
                next_task = dq.popleft()
                next_task.status = 'procesando'
                self.active[username] = next_task
                return next_task
            return None

    def get_user_snapshot(self, username):
        with self.lock:
            active_task = self.active.get(username)
            dq = list(self.pending.get(username, collections.deque()))
        return active_task, dq

    def get_full_snapshot(self):
        with self.lock:
            return dict(self.active), {u: list(dq) for u, dq in self.pending.items()}

queue_manager = QueueManager()

def advance_queue_and_continue(bot, username):
    next_task = queue_manager.advance(username)
    if next_task is None:
        return

    def run_next():
        try:
            ctx = QueueThreadContext(next_task.task_id)
            next_task.thread_ctx = ctx

            fake_message = bot.sendMessage(
                next_task.chat_id,
                '<b>🚀 ¡Tu turno en la cola! Iniciando descarga...</b>',
                parse_mode='html'
            )
            ctx.store('msg', fake_message)

            fake_update = _FakeUpdate(username, next_task.chat_id)
            ddl(fake_update, bot, fake_message, next_task.url, file_name='', thread=ctx)
        except Exception as e:
            print(f"Error al iniciar tarea encolada: {e}")
            try:
                advance_queue_and_continue(bot, username)
            except:
                pass

    t = threading.Thread(target=run_next)
    t.daemon = True
    t.start()

def expand_user_groups():
    expanded = {}
    for user_group, config in PRE_CONFIGURATED_USERS.items():
        users = [u.strip() for u in user_group.split(',')]
        for user in users:
            expanded[user] = config.copy()
    return expanded

# ==============================
# FUNCIÓN PARA VERIFICAR ESTADO DE UNA NUBE INDIVIDUAL
# ==============================
def check_single_cloud(cloud_config):
    moodle_host = cloud_config.get('moodle_host', '')
    moodle_user = cloud_config.get('moodle_user', '')
    moodle_password = cloud_config.get('moodle_password', '')
    moodle_repo_id = cloud_config.get('moodle_repo_id', '')
    proxy = cloud_config.get('proxy', '')
    
    short_name = moodle_host.replace('https://', '').replace('http://', '').strip('/')
    is_online = False
    try:
        proxy_parsed = ProxyCloud.parse(proxy) if proxy else None
        requests.get(moodle_host, timeout=5, proxies=proxy_parsed, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        
        client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
        if client.login():
            is_online = True
            try:
                client.logout()
            except:
                pass
    except Exception:
        is_online = False
        
    return {
        'host': short_name,
        'url': moodle_host,
        'online': is_online
    }

# ==============================
# TRACKER DE PROCESOS ACTIVOS
# ==============================
def update_process(thread_id, username, filename, action, current, total):
    try:
        current = int(current or 0)
        total = int(total or 0)
        percent = (current / total) * 100 if total > 0 else 0
        if percent > 100: percent = 100
        
        fmt_percent = f"{int(percent)}%" if percent.is_integer() else f"{percent:.1f}%"
        
        ACTIVE_PROCESSES[thread_id] = {
            'user': username,
            'file': filename,
            'action': action,
            'percent': fmt_percent,
            'last_update': time.time()
        }
    except: pass

def clean_process(thread_id):
    if thread_id in ACTIVE_PROCESSES:
        del ACTIVE_PROCESSES[thread_id]

# ==============================
# FUNCIÓN PARA DIVIDIR MENSAJES LARGOS
# ==============================
def send_long_message(bot, chat_id, text, original_message=None, parse_mode='html'):
    MAX_LEN = 4000
    
    if len(text) <= MAX_LEN:
        if original_message:
            bot.editMessageText(original_message, text, parse_mode=parse_mode)
        else:
            bot.sendMessage(chat_id, text, parse_mode=parse_mode)
        return

    lines = text.split('\n')
    current_msg = ""
    messages_to_send = []

    for line in lines:
        if len(current_msg) + len(line) + 1 > MAX_LEN:
            messages_to_send.append(current_msg)
            current_msg = line + '\n'
        else:
            current_msg += line + '\n'
    
    if current_msg:
        messages_to_send.append(current_msg)

    if original_message:
        bot.editMessageText(original_message, messages_to_send[0], parse_mode=parse_mode)
    else:
        bot.sendMessage(chat_id, messages_to_send[0], parse_mode=parse_mode)
        
    for msg_part in messages_to_send[1:]:
        time.sleep(0.5)
        bot.sendMessage(chat_id, msg_part, parse_mode=parse_mode)

def downloadFile(downloader,filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        thread = args[2]
        username = args[3] if len(args) > 3 else "Desconocido"
        if thread.getStore('stop'):
            downloader.stop()
            raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
        
        update_process(thread.id, username, filename, '📥 Descargando', currentBits, totalBits)
        
        downloadingInfo = infos.createDownloading(filename,totalBits,currentBits,speed,time,tid=thread.id)
        bot.editMessageText(message, downloadingInfo, parse_mode='html')
    except StopUploadException:
        raise
    except Exception as ex: 
        raise ex

def uploadFile(filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        originalfile = args[2]
        thread = args[3]
        username = args[4] if len(args) > 4 else "Desconocido"
        
        if thread and thread.getStore('stop'):
            raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
        
        update_process(thread.id, username, filename, '📤 Subiendo', currentBits, totalBits)
        
        tid_str = thread.id if thread else ''
        uploadingInfo = infos.createUploading(filename, totalBits, currentBits, speed, time, originalfile, tid=tid_str)
        bot.editMessageText(message, uploadingInfo, parse_mode='html')
    except StopUploadException:
        raise
    except Exception as ex: 
        raise ex

def processUploadFiles(filename,filesize,files,update,bot,message,thread=None):
    try:
        prep_msg = '<b>⬆️ Preparando para subir...</b>'
        if thread:
            prep_msg += f"\n\n/cancel_{thread.id}"
        bot.editMessageText(message, prep_msg, parse_mode='html')
        
        username = update.message.sender.username
        if thread:
            if thread.getStore('stop'):
                raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
            update_process(thread.id, username, os.path.basename(str(filename)), '⬆️ Preparando para subir', 0, 100)
            
        fileid = None
        user_info = get_user_info(username)
        proxy = ProxyCloud.parse(user_info['proxy']) if user_info and user_info.get('proxy') else None
        upload_type = user_info.get('uploadtype', 'evidence') if user_info else 'evidence'
        
        try:
            test_url = user_info['moodle_host']
            requests.get(test_url, timeout=6, proxies=proxy, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        except requests.exceptions.Timeout:
            if thread and thread.getStore('stop'):
                return None
            clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if user_info else "Desconocido"
            filename_fail = os.path.basename(str(filename)) if filename else "Desconocido"
            error_desc = "<b>Tiempo de espera agotado. El servidor tardó demasiado en responder.</b>"
            
            error_msg_user = (
                f"<b>❌ ¡Error de conexión con Moodle (Timeout)!</b>\n\n"
                f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
                f"⚠️ <b>Detalle:</b> {error_desc}\n\n"
                f"💡 <i>Usa /status para revisar el estado o /cambiar para elegir otra nube.</i>"
            )
            bot.editMessageText(message, error_msg_user, parse_mode='html')
            
            if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                try:
                    mensaje_log = (
                        f"<b>❌ ¡Error de Conexión (Timeout)!</b>\n\n"
                        f"👤 <b>Usuario:</b> <b>@{username}</b>\n"
                        f"📄 <b>Nombre:</b> <b>{filename_fail}</b>\n"
                        f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
                        f"⚠️ <b>Detalle:</b> {error_desc}"
                    )
                    bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                except Exception as e:
                    print(f"Error al notificar Moodle caída al grupo: {e}")
            return "LOGIN_FAILED"
        except Exception as conn_err:
            if thread and thread.getStore('stop'):
                return None
            clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if user_info else "Desconocido"
            filename_fail = os.path.basename(str(filename)) if filename else "Desconocido"
            error_desc = "<b>La plataforma Moodle no responde (Servidor caído o inaccesible).</b>"
            
            error_msg_user = (
                f"<b>❌ ¡Error de conexión con Moodle (Servidor Caído)!</b>\n\n"
                f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
                f"⚠️ <b>Detalle:</b> {error_desc}\n\n"
                f"💡 <i>Usa /status para revisar el estado o /cambiar para elegir otra nube.</i>"
            )
            bot.editMessageText(message, error_msg_user, parse_mode='html')
            
            if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                try:
                    mensaje_log = (
                        f"<b>❌ ¡Error de Conexión (Servidor Caído)!</b>\n\n"
                        f"👤 <b>Usuario:</b> <b>@{username}</b>\n"
                        f"📄 <b>Nombre:</b> <b>{filename_fail}</b>\n"
                        f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
                        f"⚠️ <b>Detalle:</b> {error_desc}"
                    )
                    bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                except Exception as e:
                    print(f"Error al notificar Moodle caída al grupo: {e}")
            return "LOGIN_FAILED"
        
        client = MoodleClient(user_info['moodle_user'],
                              user_info['moodle_password'],
                              user_info['moodle_host'],
                              user_info['moodle_repo_id'],
                              proxy=proxy)
        
        if thread and thread.getStore('stop'):
            return None

        loged = client.login()
        
        if thread and thread.getStore('stop'):
            return None

        if loged:
            evidence = None
            internal_evidname = ''
            if upload_type == 'evidence':
                evidences = client.getEvidences()
                original_evidname = str(filename).split('.')[0]
                internal_evidname = f"{original_evidname}{USER_EVIDENCE_MARKER}{username}"
                for evid in evidences:
                    if evid['name'] == internal_evidname:
                        evidence = evid
                        break
                if evidence is None:
                    evidence = client.createEvidence(internal_evidname)

            originalfile = ''
            if len(files)>1:
                originalfile = filename
            draftlist = []
            for f in files:
                if thread and thread.getStore('stop'):
                    raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
                tokenize = False
                if user_info['tokenize']!=0:
                   tokenize = True
                resp = None
                iter = 0
                while resp is None:
                    if thread and thread.getStore('stop'):
                        raise StopUploadException("Tarea detenida por mantenimiento o cancelación")

                    if upload_type == 'evidence':
                        fileid,resp = client.upload_file(f,evidence,fileid,progressfunc=uploadFile,args=(bot,message,originalfile,thread,username),tokenize=tokenize)
                    elif upload_type == 'calendar':
                        _,resp = client.upload_file_calendar(f,progressfunc=uploadFile,args=(bot,message,originalfile,thread,username),tokenize=tokenize)
                    else:
                        fileid,resp = client.upload_file_draft(f,None,fileid,progressfunc=uploadFile,args=(bot,message,originalfile,thread,username),tokenize=tokenize)
                    
                    if thread and thread.getStore('stop'):
                        raise StopUploadException("Tarea detenida por mantenimiento o cancelación")

                    iter += 1
                    if resp is None and iter>=10:
                        break
                
                if resp:
                    resp['name'] = resp.get('file', os.path.basename(str(f)))
                    draftlist.append(resp)
                
                os.unlink(f)
            
            if thread and thread.getStore('stop'):
                raise StopUploadException("Tarea detenida por mantenimiento o cancelación")

            if upload_type == 'evidence' and evidence:
                try:
                    if not evidence.get('files'):
                        evidence['files'] = fileid
                    client.saveEvidence(evidence)
                except:pass

            return {'type': upload_type, 'files': draftlist, 'evidence': evidence, 'evidname': internal_evidname}
        else:
            if thread and thread.getStore('stop'):
                return None
            
            clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if user_info else "Desconocido"
            filename_fail = os.path.basename(str(filename)) if filename else "Desconocido"
            error_desc = "<b>Error en la autenticación o credenciales incorrectas.</b>"
            error_msg_user = (
                f"<b>❌ ¡Error de Autenticación en Moodle!</b>\n\n"
                f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
                f"⚠️ <b>Detalle:</b> {error_desc}"
            )
            bot.editMessageText(message, error_msg_user, parse_mode='html')
            
            if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                try:
                    mensaje_log = (f"<b>❌ ¡Error de Autenticación en Moodle!</b>\n\n"
                                   f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                   f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
                                   f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                                   f"<b>⚠️ Detalle:</b> {error_desc}")
                    bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                except Exception as e:
                    print(f"Error al notificar error de página al grupo: {e}")
            return "LOGIN_FAILED"
    except Exception as ex:
        if thread and thread.getStore('stop'):
            if not thread.getStore('cancelled'):
                try:
                    p_act = ACTIVE_PROCESSES.get(thread.id, {}).get('action', '') if thread else ''
                    if 'Comprimiendo' in p_act:
                        cancel_txt = '<b>⚠️ Compresión cancelada.</b>'
                    elif 'Subiendo' in p_act or 'Preparando' in p_act:
                        cancel_txt = '<b>⚠️ Subida cancelada.</b>'
                    elif 'Descargando' in p_act:
                        cancel_txt = '<b>⚠️ Descarga cancelada.</b>'
                    else:
                        cancel_txt = '<b>⚠️ Tarea cancelada.</b>'
                    bot.editMessageText(message, cancel_txt, parse_mode='html')
                    thread.store('cancelled', True)
                except:
                    pass
            return None

        error_detail = str(ex) if str(ex) else "Error desconocido en la subida"
        u_info = get_user_info(username)
        clean_host = u_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if u_info else "Desconocido"
        filename_fail = os.path.basename(str(filename)) if filename else "Desconocido"

        error_msg_user = (
            f"<b>❌ ¡Error en la subida!</b>\n\n"
            f"📄 <b>Nombre:</b> <b>{filename_fail}</b>\n"
            f"☁️ <b>Nube:</b> <code>{clean_host}</code>\n"
            f"⚠️ <b>Detalle:</b> <b>Fallo en la subida del archivo: {error_detail}</b>"
        )
        bot.editMessageText(message, error_msg_user, parse_mode='html')

        if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
            try:
                mensaje_log = (f"<b>❌ ¡Error en la subida!</b>\n\n"
                               f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                               f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
                               f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                               f"<b>⚠️ Detalle:</b> <b>Fallo en la subida del archivo: {error_detail}</b>")
                bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
            except Exception as e:
                print(f"Error al notificar error de subida al grupo: {e}")
        return None

def split_raw_file(file_path, max_part_size, thread=None):
    """Divide un archivo sin comprimirlo ni envolverlo en otro formato."""
    parts = []
    index = 1
    with open(file_path, 'rb') as src:
        while True:
            if thread and thread.getStore('stop'):
                raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
            data = src.read(max_part_size)
            if not data:
                break
            part_path = f"{file_path}.part{index:03d}"
            with open(part_path, 'wb') as dst:
                dst.write(data)
            parts.append(part_path)
            index += 1
    return parts


def processFile(update,bot,message,file,thread=None):
    phase = "procesamiento"
    findex = 0
    getUser = None
    username = update.message.sender.username
    try:
        if thread and thread.getStore('stop'):
            raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
            
        file_size = get_file_size(file)
        getUser = get_user_info(username)
        # Cada nube usa su propio límite configurado como tamaño máximo de
        # parte. Así un archivo menor que la cuota se sube en una sola pieza,
        # mientras que los archivos mayores se dividen según esa nube.
        configured_limit = 1024 * 1024 * int(getUser.get('zips', 250))
        max_file_size = configured_limit
        file_upload_count = 0
        upload_result = None
        
        if file_size > max_file_size:
            phase = "particionado"
            compresingInfo = infos.createCompresing(file,file_size,max_file_size)
            if thread:
                compresingInfo = compresingInfo.strip() + f"\n\n/cancel_{thread.id}"
            bot.editMessageText(message, compresingInfo, parse_mode='html')
            
            if thread:
                if thread.getStore('stop'):
                    raise StopUploadException("Tarea detenida por mantenimiento o cancelación")
                update_process(thread.id, username, os.path.basename(file), '📦 Particionando', 0, 100)

            raw_parts = split_raw_file(file, max_file_size, thread=thread)

            phase = "subida"
            upload_result = processUploadFiles(file,file_size,raw_parts,update,bot,message,thread=thread)
            try:
                os.unlink(file)
            except:pass
            file_upload_count = len(raw_parts)
        else:
            phase = "subida"
            upload_result = processUploadFiles(file,file_size,[file],update,bot,message,thread=thread)
            file_upload_count = 1
        
        if thread and thread.getStore('stop'):
            raise StopUploadException("Tarea detenida por mantenimiento o cancelación")

        files = []
        if upload_result == "LOGIN_FAILED":
            return
        if upload_result:
            upload_type = upload_result.get('type', 'evidence')
            
            if upload_type == 'evidence':
                internal_evidname = upload_result.get('evidname', '')
                try:
                    proxy = ProxyCloud.parse(getUser['proxy']) if getUser.get('proxy') else None
                    moodle_client = MoodleClient(getUser['moodle_user'],
                                                 getUser['moodle_password'],
                                                 getUser['moodle_host'],
                                                 getUser['moodle_repo_id'],
                                                 proxy=proxy)
                    if moodle_client.login():
                        evidence_index = -1
                        max_attempts = 8
                        for attempt in range(max_attempts):
                            evidences = moodle_client.getEvidences()
                            for idx, ev in enumerate(evidences):
                                if ev['name'] == internal_evidname:
                                    files = ev.get('files', [])
                                    if files:
                                        evidence_index = idx
                                        break
                            if files:
                                break
                            time.sleep(2)

                        if not files:
                            print(f"⚠️ No se pudieron obtener los archivos de la evidencia '{internal_evidname}' tras {max_attempts} intentos")
                        
                        if files:
                            for i in range(len(files)):
                                url = files[i]['directurl']
                                if 'draftfile.php' in url and 'webservice/' not in url:
                                    url = url.replace('draftfile.php', 'webservice/draftfile.php')
                                if 'pluginfile.php' in url and 'webservice/' not in url:
                                    url = url.replace('pluginfile.php', 'webservice/pluginfile.php')
                                if '?forcedownload=1' in url:
                                    url = url.replace('?forcedownload=1', '')
                                elif '&forcedownload=1' in url:
                                    url = url.replace('&forcedownload=1', '')
                                if '&token=' in url and '?' not in url:
                                    url = url.replace('&token=', '?token=', 1)
                                files[i]['directurl'] = url
                        
                        moodle_client.logout()
                        
                        findex = evidence_index if evidence_index != -1 else 0
                except Exception as e:
                    print(f"Error obteniendo índice de evidencia: {e}")
                    findex = 0
            else:
                for item in upload_result.get('files', []):
                    if not item:
                        continue
                    raw_url = item.get('url', '')
                    
                    if 'draftfile.php' in raw_url and 'webservice/' not in raw_url:
                        raw_url = raw_url.replace('draftfile.php', 'webservice/draftfile.php')
                    if 'pluginfile.php' in raw_url and 'webservice/' not in raw_url:
                        raw_url = raw_url.replace('pluginfile.php', 'webservice/pluginfile.php')

                    if '?forcedownload=1' in raw_url:
                        raw_url = raw_url.replace('?forcedownload=1', '')
                    elif '&forcedownload=1' in raw_url:
                        raw_url = raw_url.replace('&forcedownload=1', '')
                    if '&token=' in raw_url and '?' not in raw_url:
                        raw_url = raw_url.replace('&token=', '?token=', 1)
                    
                    files.append({
                        'name': item.get('name', os.path.basename(str(file))),
                        'url': item.get('normalurl', ''),
                        'directurl': raw_url
                    })
                findex = 0

            # El bot original no levantaba un proxy HTTP: devolvía un código
            # lógico único con las partes ordenadas. El descargador compatible
            # interpreta ese código y concatena los bytes en streaming.
            if file_upload_count > 1 and files:
                from chunk_code import build_code
                part_urls = []
                for index, part in enumerate(files, 1):
                    part_url = part.get('directurl') or part.get('url')
                    if part_url:
                        part_urls.append({'index': index, 'url': part_url})
                if len(part_urls) == file_upload_count:
                    one_code = build_code(
                        os.path.basename(file), file_size, part_urls
                    )
                    files = [{
                        'name': os.path.basename(file),
                        'url': one_code,
                        'directurl': one_code,
                    }]
            
            if thread and thread.getStore('stop'):
                raise StopUploadException("Tarea detenida por mantenimiento o cancelación")

            bot.deleteMessage(message.chat.id,message.message_id)
            finishInfo = infos.createFinishUploading(file,file_size,max_file_size,file_upload_count,file_upload_count,findex)
            filesInfo = infos.createFileMsg(file,files)
            
            extra_msg = ""
            if getUser:
                host = getUser.get('moodle_host', '').lower()
                if 'fundacion.uh.cu' in host:
                    m_user = getUser.get('moodle_user', '')
                    m_pass = getUser.get('moodle_password', '')
                    extra_msg = f"\n<b>⚠️ Debes iniciar sesión con la cuenta en la plataforma para poder descargar:</b>\n\n<b>👤 Usuario:</b> <code>{m_user}</code>\n<b>🔑 Contraseña:</b> <code>{m_pass}</code>\n"

            mensaje_final = finishInfo + '\n' + extra_msg + '\n' + filesInfo
            try:
                bot.sendMessage(message.chat.id, mensaje_final, parse_mode='html')
            except Exception as e:
                print(f"Error enviando mensaje de finalización (probable HTML inválido en nombre/URL): {e}")
                try:
                    plano = re.sub('<[^<]+?>', '', mensaje_final)
                    bot.sendMessage(message.chat.id, plano)
                except Exception as e2:
                    print(f"Fallback de mensaje de finalización también falló: {e2}")
            
            filename_clean = os.path.basename(file)
            memory_stats.log_upload(
                username=username,
                filename=filename_clean,
                file_size=file_size,
                moodle_host=getUser['moodle_host']
            )

            if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                try:
                    clean_host = getUser['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                    mensaje_log = (f"<b>✅ ¡Subida completada!</b>\n\n"
                                   f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                   f"<b>📄 Nombre:</b> <b>{filename_clean}</b>\n"
                                   f"<b>⚖️ Peso:</b> <b>{format_file_size(file_size)}</b>\n"
                                   f"<b>☁️ Nube:</b> <code>{clean_host}</code>")
                    bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                except Exception as e:
                    print(f"Error al notificar subida al grupo: {e}")
            
            if len(files)>0:
                txtname = str(file).split('/')[-1].split('.')[0] + '.txt'
                send_to_group_flag = False if username.lower() == ADMIN_USERNAME.lower() else True
                sendTxt(txtname, files, update, bot, send_to_group=send_to_group_flag, user_info=getUser)
            
            send_sticker(message.chat.id, "CAACAgEAAxkBAAIoXGqA9r31O2plFhlz_RG3tuYEg-_JAAK6BgACnFgJRDiBixe0VxapPQQ")
        else:
            if thread and thread.getStore('stop'):
                pass
            else:
                clean_host = getUser['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if getUser else "Desconocido"
                error_page_msg = (
                    f"<b>❌ ¡Error de Autenticación en Moodle!</b>\n\n"
                    f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                    f"<b>⚠️ Detalle:</b> <b>Error en la autenticación o credenciales incorrectas</b>"
                )
                bot.editMessageText(message, error_page_msg, parse_mode='html')
    except Exception as ex:
        if thread and thread.getStore('stop'):
            if not thread.getStore('cancelled'):
                try:
                    p_act = ACTIVE_PROCESSES.get(thread.id, {}).get('action', '') if thread else ''
                    if 'Comprimiendo' in p_act:
                        cancel_txt = '<b>⚠️ Compresión cancelada.</b>'
                    elif 'Subiendo' in p_act or 'Preparando' in p_act:
                        cancel_txt = '<b>⚠️ Subida cancelada.</b>'
                    elif 'Descargando' in p_act:
                        cancel_txt = '<b>⚠️ Descarga cancelada.</b>'
                    else:
                        cancel_txt = '<b>⚠️ Tarea cancelada.</b>'
                    bot.editMessageText(message, cancel_txt, parse_mode='html')
                    thread.store('cancelled', True)
                except:
                    pass
            return

        error_detail = str(ex) if str(ex) else "Error desconocido"
        print(f"Proceso detenido o error en {phase}: {ex}")
        
        clean_host = getUser['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if getUser else "Desconocido"
        filename_fail = os.path.basename(file) if file else "Desconocido"
        
        error_msg_user = (
            f"<b>❌ ¡Error en la {phase}!</b>\n\n"
            f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
            f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
            f"<b>⚠️ Detalle:</b> <b>Fallo en la {phase} del archivo: {error_detail}</b>"
        )
        bot.editMessageText(message, error_msg_user, parse_mode='html')
        
        if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
            try:
                mensaje_log = (f"<b>❌ ¡Error en la {phase}!</b>\n\n"
                               f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                               f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
                               f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                               f"<b>⚠️ Detalle:</b> <b>Fallo en la {phase} del archivo: {error_detail}</b>")
                bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
            except Exception as e:
                print(f"Error al notificar error de proceso al grupo: {e}")
    finally:
        if thread:
            clean_process(thread.id)

def ddl(update,bot,message,url,file_name='',thread=None):
    username = update.message.sender.username
    downloader = Downloader()
    if thread and hasattr(thread, 'store'):
        thread.store('downloader', downloader)

    try:
        file = None
        retries = 3
        for attempt in range(retries):
            try:
                if thread and thread.getStore('stop'):
                    break
                if attempt > 0:
                    try:
                        bot.editMessageText(message, f"<b>⚠️ Error de conexión, reintentando... (Intento {attempt+1}/{retries})</b>", parse_mode='html')
                    except: pass
                    if thread:
                        update_process(thread.id, username, "Descarga", f'🔄 Reintentando ({attempt+1}/{retries})', 0, 100)
                
                file = downloader.download_url(url, progressfunc=downloadFile, args=(bot,message,thread,username))
                if file:
                    break
            except Exception as ex:
                error_detail = str(ex) if str(ex) else "Error desconocido"
                if attempt == retries - 1:
                    u_info = get_user_info(username)
                    clean_host = u_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/') if u_info else "Desconocido"
                    filename_fail = url.split('/')[-1] or "Desconocido"

                    error_msg_user = (
                        f"<b>❌ ¡Error en la descarga!</b>\n\n"
                        f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
                        f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                        f"<b>⚠️ Detalle:</b> <b>Fallo en la descarga del enlace tras {retries} intentos: {error_detail}</b>"
                    )
                    try:
                        bot.editMessageText(message, error_msg_user, parse_mode='html')
                    except: pass
                    
                    if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                        try:
                            mensaje_log = (f"<b>❌ ¡Error en la descarga!</b>\n\n"
                                           f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                           f"<b>📄 Nombre:</b> <b>{filename_fail}</b>\n"
                                           f"<b>☁️ Nube:</b> <code>{clean_host}</code>\n"
                                           f"<b>⚠️ Detalle:</b> <b>Fallo en la descarga del enlace: {error_detail}</b>")
                            bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar error de descarga al grupo: {e}")
                    
                    raise ex
                time.sleep(3)
        
        if not downloader.stoping:
            if file:
                processFile(update,bot,message,file,thread=thread)
            else:
                detail = downloader.last_error or "la fuente no respondió con un archivo descargable"
                error_text = (
                    "<b>❌ Error en la descarga.</b>\n\n"
                    f"<b>⚠️ Detalle:</b> <code>{html.escape(detail)}</code>"
                )
                try:
                    bot.editMessageText(message, error_text, parse_mode='html')
                except:
                    bot.editMessageText(message, error_text, parse_mode='html')
    except Exception as ex:
        if thread and thread.getStore('stop'):
            if not thread.getStore('cancelled'):
                try:
                    p_act = ACTIVE_PROCESSES.get(thread.id, {}).get('action', '') if thread else ''
                    if 'Descargando' in p_act:
                        cancel_txt = '<b>⚠️ Descarga cancelada.</b>'
                    else:
                        cancel_txt = '<b>⚠️ Tarea cancelada.</b>'
                    bot.editMessageText(message, cancel_txt, parse_mode='html')
                    thread.store('cancelled', True)
                except:
                    pass
        else:
            print(f"Error en ddl: {ex}")
    finally:
        if thread:
            clean_process(thread.id)
        advance_queue_and_continue(bot, username)

def sendTxt(name, files, update, bot, send_to_group=False, user_info=None):
    txt = open(name,'w')
    
    for i, f in enumerate(files):
        url = f['directurl']
        
        if 'draftfile.php' in url and 'webservice/' not in url:
            url = url.replace('draftfile.php', 'webservice/draftfile.php')
        if 'pluginfile.php' in url and 'webservice/' not in url:
            url = url.replace('pluginfile.php', 'webservice/pluginfile.php')
        
        if '?forcedownload=1' in url:
            url = url.replace('?forcedownload=1', '')
        elif '&forcedownload=1' in url:
            url = url.replace('&forcedownload=1', '')
        
        if '&token=' in url and '?' not in url:
            url = url.replace('&token=', '?token=', 1)
        
        txt.write(url)
        
        if i < len(files) - 1:
            txt.write('\n\n')
    
    txt.close()
    
    bot.sendFile(update.message.chat.id, name)
    
    if send_to_group and LOG_GROUP_ID != 0:
        try:
            bot.sendFile(LOG_GROUP_ID, name)
        except Exception as e:
            print(f"Error enviando txt al grupo: {e}")
            
    os.unlink(name)

def delete_message_after_delay(bot, chat_id, message_id, delay=8):
    def delete():
        time.sleep(delay)
        try:
            bot.deleteMessage(chat_id, message_id)
        except Exception as e:
            print(f"Error al eliminar mensaje: {e}")
    
    thread = threading.Thread(target=delete)
    thread.daemon = True
    thread.start()

def get_all_cloud_evidences_fast(use_cache=True):
    if use_cache and not cloud_cache.should_refresh():
        cached_data = cloud_cache.get_cache('all_clouds')
        if cached_data:
            return cached_data
    
    all_evidences = []
    
    for user_group, cloud_config in PRE_CONFIGURATED_USERS.items():
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        if use_cache and not cloud_cache.should_refresh(moodle_host):
            cached_evidence = cloud_cache.get_cache(moodle_host)
            if cached_evidence:
                all_evidences.extend(cached_evidence)
                continue
        
        try:
            proxy_parsed = ProxyCloud.parse(proxy) if proxy else None
            requests.get(moodle_host, timeout=5, proxies=proxy_parsed, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
            
            client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
            
            if client.login():
                evidences = client.getEvidences()
                
                for evidence in evidences:
                    evidence_info = {
                        'cloud_name': moodle_host,
                        'cloud_user': moodle_user,
                        'evidence_name': evidence.get('name', 'Sin nombre'),
                        'files_count': len(evidence.get('files', [])),
                        'evidence_data': evidence,
                        'group_users': user_group.split(','),
                        'cloud_config': cloud_config
                    }
                    all_evidences.append(evidence_info)
                
                client.logout()
                if use_cache:
                    cloud_cache.update_cache(moodle_host, [ev for ev in all_evidences if ev['cloud_name'] == moodle_host])
            else:
                print(f"No se pudo conectar a {moodle_host}")
                
        except Exception as e:
            print(f"Error obteniendo evidencias de {moodle_host}: {str(e)}")
    
    if use_cache:
        cloud_cache.update_full_cache(all_evidences)
    
    return all_evidences

def delete_evidence_from_cloud(cloud_config, evidence):
    try:
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        proxy_parsed = ProxyCloud.parse(proxy) if proxy else None
        requests.get(moodle_host, timeout=5, proxies=proxy_parsed, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        
        client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
        
        if client.login():
            all_evidences = client.getEvidences()
            evidence_to_delete = None
            
            for ev in all_evidences:
                if ev.get('id') == evidence.get('id'):
                    evidence_to_delete = ev
                    break
            
            if evidence_to_delete:
                evidence_name = evidence_to_delete.get('name', '')
                files_count = len(evidence_to_delete.get('files', []))
                client.deleteEvidence(evidence_to_delete)
                client.logout()
                cloud_cache.clear_cache()
                return True, evidence_name, files_count
            else:
                client.logout()
                return False, "", 0
        else:
            return False, "", 0
            
    except Exception as e:
        return False, f"Error: {str(e)}", 0

def delete_all_evidences_from_cloud(cloud_config):
    try:
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        proxy_parsed = ProxyCloud.parse(proxy) if proxy else None
        requests.get(moodle_host, timeout=5, proxies=proxy_parsed, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        
        client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
        
        if client.login():
            all_evidences = client.getEvidences()
            deleted_count = 0
            total_files = 0
            
            for evidence in all_evidences:
                try:
                    files_count = len(evidence.get('files', []))
                    client.deleteEvidence(evidence)
                    deleted_count += 1
                    total_files += files_count
                except:
                    pass
            
            client.logout()
            cloud_cache.clear_cache()
            return True, deleted_count, total_files
        else:
            return False, 0, 0
            
    except Exception as e:
        return False, 0, 0

class AdminEvidenceManager:
    def __init__(self):
        self.current_list = []
        self.clouds_dict = {}
        self.last_update = None
    
    def refresh_data(self, force=False):
        if not force and not cloud_cache.should_refresh():
            return len(self.current_list)
        
        try:
            all_evidences = get_all_cloud_evidences_fast(use_cache=True)
            self.clouds_dict = {}
            
            for evidence in all_evidences:
                cloud_name = evidence['cloud_name']
                if cloud_name not in self.clouds_dict:
                    self.clouds_dict[cloud_name] = []
                self.clouds_dict[cloud_name].append(evidence)
            
            self.current_list = []
            cloud_index = 0
            for cloud_name, evidences in self.clouds_dict.items():
                for idx, evidence in enumerate(evidences):
                    self.current_list.append({
                        'cloud_idx': cloud_index,
                        'evid_idx': idx,
                        'cloud_name': cloud_name,
                        'evidence': evidence
                    })
            
            self.last_update = datetime.datetime.now()
            return len(self.current_list)
        except Exception as e:
            print(f"Error refrescando datos: {e}")
            return len(self.current_list)
    
    def get_evidence(self, cloud_idx, evid_idx):
        try:
            if cloud_idx is None or evid_idx is None:
                return None
                
            if cloud_idx < len(self.clouds_dict):
                cloud_name = list(self.clouds_dict.keys())[cloud_idx]
                if evid_idx < len(self.clouds_dict[cloud_name]):
                    return self.clouds_dict[cloud_name][evid_idx]
        except Exception as e:
            print(f"Error obteniendo evidencia: {e}")
        return None
    
    def get_txt_for_evidence(self, cloud_idx, evid_idx):
        evidence = self.get_evidence(cloud_idx, evid_idx)
        if evidence:
            try:
                cloud_config = evidence['cloud_config']
                evidence_data = evidence['evidence_data']
                
                moodle_host = cloud_config.get('moodle_host', '')
                moodle_user = cloud_config.get('moodle_user', '')
                moodle_password = cloud_config.get('moodle_password', '')
                moodle_repo_id = cloud_config.get('moodle_repo_id', '')
                proxy = cloud_config.get('proxy', '')
                
                proxy_parsed = ProxyCloud.parse(proxy) if proxy else None
                requests.get(moodle_host, timeout=5, proxies=proxy_parsed, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
                
                client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
                
                if client.login():
                    all_evidences = client.getEvidences()
                    current_evidence = None
                    
                    for ev in all_evidences:
                        if ev.get('id') == evidence_data.get('id'):
                            current_evidence = ev
                            break
                    
                    if current_evidence:
                        files = current_evidence.get('files', [])
                        
                        for i in range(len(files)):
                            url = files[i]['directurl']
                            if 'draftfile.php' in url and 'webservice/' not in url:
                                url = url.replace('draftfile.php', 'webservice/draftfile.php')
                            if 'pluginfile.php' in url and 'webservice/' not in url:
                                url = url.replace('pluginfile.php', 'webservice/pluginfile.php')
                            if '?forcedownload=1' in url:
                                url = url.replace('?forcedownload=1', '')
                            elif '&forcedownload=1' in url:
                                url = url.replace('&forcedownload=1', '')
                            if '&token=' in url and '?' not in url:
                                url = url.replace('&token=', '?token=', 1)
                            files[i]['directurl'] = url
                        
                        client.logout()
                        return files
                    client.logout()
            except Exception as e:
                print(f"Error obteniendo TXT: {e}")
        return None
    
    def clear_cache(self):
        cloud_cache.clear_cache()
        self.current_list = []
        self.clouds_dict = {}
        self.last_update = None

admin_evidence_manager = AdminEvidenceManager()

def extract_one_param_simple(msgText, prefix):
    try:
        if prefix in msgText:
            parts = msgText.split('_')
            if prefix == '/adm_cloud_':
                return int(parts[2]) if len(parts) > 2 else None
            elif prefix == '/adm_wipe_':
                return int(parts[2]) if len(parts) > 2 else None
    except (ValueError, IndexError):
        return None
    return None

def extract_two_params_simple(msgText, prefix):
    try:
        if prefix in msgText:
            parts = msgText.split('_')
            if len(parts) > 3:
                param1 = int(parts[2])
                param2 = int(parts[3])
                return [param1, param2]
    except (ValueError, IndexError):
        return None
    return None

def show_updated_cloud(bot, message, cloud_idx):
    try:
        admin_evidence_manager.refresh_data(force=True)
        cloud_names = list(admin_evidence_manager.clouds_dict.keys())
        
        if cloud_idx < 0 or cloud_idx >= len(cloud_names):
            show_updated_all_clouds(bot, message)
            return
        
        cloud_name = cloud_names[cloud_idx]
        evidences = admin_evidence_manager.clouds_dict.get(cloud_name, [])
        
        if not evidences:
            short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
            empty_msg = f"""
<b>📭 Nube vacía</b>

<b>✅ Eliminación completa</b>
☁️ <b>Nube:</b> <code>{short_name}</code>

🎉 <b>¡Has eliminado todas las evidencias de esta nube!</b>

🔄 <b>Regresando a todas las nubes...</b>
            """
            bot.editMessageText(message, empty_msg, parse_mode='html')
            time.sleep(1.5)
            show_updated_all_clouds(bot, message)
            return
        
        short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
        
        list_msg = f"""
<b>📋 Nube actualizada</b>
☁️ <b>Nube:</b> <code>{short_name}</code>

"""
        for idx, evidence in enumerate(evidences):
            ev_name = evidence['evidence_name']
            clean_name = ev_name
            user_tags = []
            
            for user in evidence['group_users']:
                marker = f"{USER_EVIDENCE_MARKER}{user}"
                if marker in ev_name:
                    clean_name = ev_name.replace(marker, "").strip()
                    user_tags.append(f"@{user}")
            
            if user_tags:
                user_str = f" ({', '.join(user_tags[:2])})"
                if len(user_tags) > 2:
                    user_str = f" ({', '.join(user_tags[:2])}...)"
            else:
                user_str = ""
            
            list_msg += f"<b>{idx}.</b> <b>{clean_name[:35]}</b>"
            if len(clean_name) > 35:
                list_msg += "..."
            list_msg += f"<b>{user_str}</b>\n"
            list_msg += f"   📁 <b>Archivos:</b> <b>{evidence['files_count']}</b>\n"
            list_msg += f"   👁️ <b>Ver:</b> /adm_show_{cloud_idx}_{idx}\n"
            list_msg += f"   📄 <b>TXT:</b> /adm_fetch_{cloud_idx}_{idx}\n"
            list_msg += f"   🗑️ <b>Borrar:</b> /adm_delete_{cloud_idx}_{idx}\n\n"
        
        total_evidences = len(evidences)
        total_files = sum(e['files_count'] for e in evidences)
        
        list_msg += f"""
🔧 <b>Acciones masivas:</b>
/adm_wipe_{cloud_idx} - <b>Eliminación masiva</b>

📊 <b>Resumen:</b>
• <b>Evidencias:</b> <b>{total_evidences}</b>
• <b>Archivos:</b> <b>{total_files}</b>
        """
        
        send_long_message(bot, message.chat.id, list_msg, original_message=message, parse_mode='html')
        
    except Exception as e:
        error_msg = f"""
<b>❌ Error al actualizar</b>
⚠️ <b>No se pudo mostrar la nube actualizada.</b>
        """
        bot.editMessageText(message, error_msg, parse_mode='html')

def show_updated_all_clouds(bot, message):
    try:
        admin_evidence_manager.refresh_data()
        total_evidences = len(admin_evidence_manager.current_list)
        total_clouds = len(admin_evidence_manager.clouds_dict)
        total_files = 0
        
        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
            for ev in evidences:
                total_files += ev['files_count']
        
        if total_evidences == 0:
            empty_msg = f"""
<b>👑 Todas las nubes actualizadas</b>
📊 <b>Resumen general:</b>
• <b>Nubes:</b> <b>{total_clouds}</b>
• <b>Evidencias totales:</b> <b>0</b>
• <b>Archivos totales:</b> <b>0</b>

<b>✅ Todas las nubes están vacías</b>
            """
            bot.editMessageText(message, empty_msg, parse_mode='html')
            return
        
        menu_msg = f"""
<b>👑 Todas las nubes actualizadas</b>
📊 <b>Resumen general:</b>
• <b>Nubes:</b> <b>{total_clouds}</b>
• <b>Evidencias totales:</b> <b>{total_evidences}</b>
• <b>Archivos totales:</b> <b>{total_files}</b>

📋 <b>Nubes disponibles:</b>"""
        
        cloud_index = 0
        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
            cloud_files = sum(ev['files_count'] for ev in evidences)
            short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
            
            menu_msg += f"\n\n<b>{cloud_index}.</b> <code>{short_name}</code>"
            menu_msg += f"\n   📁 <b>{len(evidences)} evidencias, {cloud_files} archivos</b>"
            menu_msg += f"\n   🔍 /adm_cloud_{cloud_index}"
            
            if len(evidences) > 0:
                menu_msg += f"\n   🗑️ /adm_wipe_{cloud_index}"
            
            cloud_index += 1
        
        if total_evidences > 0:
            menu_msg += f"""

🔧 <b>Opciones masivas:</b>
/adm_nuke - ⚠️ <b>Eliminación masiva</b>
        """
        
        bot.editMessageText(message, menu_msg, parse_mode='html')
        
    except Exception as e:
        bot.editMessageText(message, f'<b>❌ Error al mostrar nubes actualizadas:</b> <b>{str(e)}</b>', parse_mode='html')

def show_loading_progress(bot, message, step, total_steps=3):
    progress_chars = ['○', '◔', '◑', '◕', '●']
    progress = int((step / total_steps) * 4)
    bar = progress_chars[progress] if progress < len(progress_chars) else progress_chars[-1]
    
    loading_msgs = [
        "🔄 <b>Conectando con las nubes...</b>",
        "📊 <b>Procesando datos...</b>",
        "✅ <b>Actualizando información...</b>"
    ]
    
    msg = loading_msgs[step-1] if step <= len(loading_msgs) else f"<b>Procesando... ({step}/{total_steps})</b>"
    bot.editMessageText(message, f"{msg} {bar}", parse_mode='html')

def onmessage(update,bot:PyrogramBotClient):
    global MAINTENANCE_MODE, BANNED_USERS, REMOVED_USERS, ACTIVE_PROCESSES, ACTIVE_STATUS_CHECKS, CHANGING_CLOUD_USERS
    try:
        thread = bot.this_thread
        username = update.message.sender.username
        chat_id = update.message.chat.id

        msgText = ''
        try: msgText = update.message.text
        except:pass
        
        expanded_users = expand_user_groups()
        
        has_access = False
        if username:
            if username.lower() == ADMIN_USERNAME.lower():
                has_access = True
            elif username.lower() in {b.lower() for b in BANNED_USERS}:
                bot.sendMessage(chat_id, '<b>🚫 Has sido baneado y no puedes usar este bot.</b>', parse_mode='html')
                return
            elif username.lower() in {u.lower() for u in REMOVED_USERS}:
                has_access = False
            else:
                for u in expanded_users.keys():
                    if u.lower() == username.lower():
                        has_access = True
                        break
                if not has_access and get_user_info(username) is not None:
                    has_access = True

        if not has_access:
            bot.sendMessage(chat_id, '<b>🚫 No tienes acceso a este bot.</b>', parse_mode='html')
            return

        if MAINTENANCE_MODE and username.lower() != ADMIN_USERNAME.lower():
            bot.sendMessage(chat_id, 
                "🛠️ <b>¡Sistema en mantenimiento temporal!</b>\n\n"
                "⚠️ <b>El bot se encuentra actualmente bajo labores de optimización y mantenimiento.</b>\n"
                "⏳ <b>Por favor, intenta de nuevo más tarde. Disculpa las molestias ocasionadas.</b>", 
                parse_mode='html')
            return
        
        user_info = get_user_info(username)
        if user_info.get('chat_id') != chat_id:
            user_info['chat_id'] = chat_id
            USER_CLOUD_OVERRIDES[username.lower()] = user_info

        # Pyrogram entrega documentos y vídeos como archivos reales. El
        # cliente anterior solo examinaba texto, por lo que esos mensajes se
        # ignoraban. Descargarlos primero permite usar el mismo flujo Moodle
        # que ya procesa los enlaces externos.
        media = (
            getattr(update.message, 'document', None)
            or getattr(update.message, 'video', None)
            or getattr(update.message, 'audio', None)
            or getattr(update.message, 'animation', None)
        )
        if media:
            original_name = getattr(media, 'file_name', None) or f"archivo_{update.message.message_id}"
            original_name = os.path.basename(str(original_name)).replace('/', '_').replace('\\\\', '_')
            os.makedirs('/tmp/upload_et', exist_ok=True)
            local_path = os.path.join('/tmp/upload_et', f"{createID(12)}_{original_name}")
            progress_message = bot.sendMessage(chat_id, '<b>📥 Recibiendo archivo...</b>', parse_mode='html')
            thread.store('msg', progress_message)
            downloaded_path = bot.downloadMessage(update.message, local_path)
            if downloaded_path and os.path.isfile(downloaded_path):
                processFile(update, bot, progress_message, downloaded_path, thread=thread)
            else:
                bot.editMessageText(progress_message, '<b>❌ No se pudo recibir el archivo.</b>', parse_mode='html')
            return

        if '/cancel_' in msgText:
            try:
                parts = str(msgText).strip().split('_')
                if len(parts) >= 2:
                    tid = parts[1]

                    owner_username, target_task, location = queue_manager.find_task(tid)
                    if target_task is None:
                        bot.sendMessage(chat_id, '<b>⚠️ Esta tarea ya no existe o ya finalizó.</b>', parse_mode='html')
                        return

                    is_admin_action = (username.lower() == ADMIN_USERNAME.lower() and owner_username.lower() != username.lower())

                    proc_info = ACTIVE_PROCESSES.get(tid, {})
                    proc_action = proc_info.get('action', '')

                    cancel_result = queue_manager.cancel(owner_username, tid)

                    proc_user = proc_info.get('user', owner_username)
                    proc_file = proc_info.get('file', target_task.filename)

                    clean_process(tid)

                    if cancel_result == 'pending':
                        try:
                            if is_admin_action:
                                bot.sendMessage(target_task.chat_id, f'<b>⚠️ El administrador retiró tu tarea de la cola.</b>\n\n📄 <b>{target_task.filename}</b>', parse_mode='html')
                            else:
                                bot.sendMessage(target_task.chat_id, f'<b>⚠️ Tarea retirada de la cola.</b>\n\n📄 <b>{target_task.filename}</b>', parse_mode='html')
                        except: pass
                    elif cancel_result == 'active':
                        if target_task.thread_ctx:
                            target_task.thread_ctx.store('stop', True)
                            target_task.thread_ctx.store('cancelled', True)
                            dl = target_task.thread_ctx.getStore('downloader')
                            if dl:
                                try:
                                    dl.stop()
                                except:
                                    pass
                        time.sleep(0.5)

                        stage_name = "tarea"
                        if 'Descargando' in proc_action:
                            stage_name = "descarga"
                        elif 'Comprimiendo' in proc_action:
                            stage_name = "compresión"
                        elif 'Subiendo' in proc_action or 'Preparando' in proc_action:
                            stage_name = "subida"

                        if is_admin_action:
                            if stage_name == "descarga":
                                texto_cancelado = '<b>⚠️ El administrador canceló la descarga.</b>'
                            elif stage_name == "compresión":
                                texto_cancelado = '<b>⚠️ El administrador canceló la compresión.</b>'
                            elif stage_name == "subida":
                                texto_cancelado = '<b>⚠️ El administrador canceló la subida.</b>'
                            else:
                                texto_cancelado = '<b>⚠️ El administrador canceló tu tarea.</b>'
                        else:
                            if stage_name == "descarga":
                                texto_cancelado = '<b>⚠️ Descarga cancelada.</b>'
                            elif stage_name == "compresión":
                                texto_cancelado = '<b>⚠️ Compresión cancelada.</b>'
                            elif stage_name == "subida":
                                texto_cancelado = '<b>⚠️ Subida cancelada.</b>'
                            else:
                                texto_cancelado = '<b>⚠️ Tarea cancelada.</b>'

                        if target_task.thread_ctx:
                            msg_obj = target_task.thread_ctx.getStore('msg')
                            if msg_obj:
                                try:
                                    bot.editMessageText(msg_obj, texto_cancelado, parse_mode='html')
                                except: pass

                    if LOG_GROUP_ID != 0 and proc_user.lower() != ADMIN_USERNAME.lower() and not is_admin_action:
                        try:
                            mensaje_log = (f"<b>❌ ¡Proceso cancelado!</b>\n\n"
                                           f"<b>👤 Usuario:</b> <b>@{proc_user}</b>\n"
                                           f"<b>🛠️ Acción:</b> <b>{proc_action}</b>\n"
                                           f"<b>📄 Archivo:</b> <b>{proc_file}</b>")
                            bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar cancelación al grupo: {e}")

            except Exception as ex:
                print(str(ex))
            return

        message = bot.sendMessage(chat_id,'<b>✨Procesando solicitud...✨</b>', parse_mode='html')
        thread.store('msg',message)

        # ============================================
        # COMPROBACIONES Y RECTIFICACIÓN DE COMANDOS ADMIN
        # ============================================
        if username.lower() == ADMIN_USERNAME.lower():
            if msgText.lower().startswith('/add'):
                parts = msgText.replace('/add', '').strip().split()
                if len(parts) < 2:
                    guide_msg = (
                        "<b>❌ Formato incorrecto para /add.</b>\n\n"
                        "💡 <b>Uso correcto:</b> <code>/add usuario1,usuario2 [número_de_nube]</code>\n"
                        "<b>Ejemplo:</b> <code>/add Pedro,Maria 1</code>\n\n"
                        "ℹ️ <i>Usa /adm_userclouds para revisar los números de nubes disponibles.</i>"
                    )
                    bot.editMessageText(message, guide_msg, parse_mode='html')
                    return
                try:
                    users_part = parts[0]
                    cloud_num_part = parts[1]
                    if not cloud_num_part.isdigit():
                        raise ValueError()
                    cloud_idx = int(cloud_num_part) - 1
                    if not (0 <= cloud_idx < len(AVAILABLE_CLOUDS)):
                        raise ValueError()
                    selected_cloud = AVAILABLE_CLOUDS[cloud_idx]
                    usernames = [u.strip().lstrip('@') for u in users_part.split(',')]
                    usernames = [u for u in usernames if u]
                    
                    if not usernames:
                        bot.editMessageText(message, "<b>❌ No se especificaron usuarios válidos.</b>\n💡 <b>Uso correcto:</b> /add usuario1,usuario2 1", parse_mode='html')
                        return

                    if any(u.lower() == ADMIN_USERNAME.lower() for u in usernames):
                        bot.editMessageText(message, f'🛡️ <b>Acción denegada:</b> <b>No es posible agregar al usuario administrador (@{ADMIN_USERNAME}).</b>', parse_mode='html')
                        return

                    banned_lower = {b.lower() for b in BANNED_USERS}
                    banned_found = [u for u in usernames if u.lower() in banned_lower]
                    if banned_found:
                        banned_str = ", ".join([f"@{u}" for u in banned_found])
                        bot.editMessageText(message, f"<b>❌ Los usuarios</b> {banned_str} <b>están baneados y no se pueden agregar.</b>", parse_mode='html')
                        return

                    already_has_access = []
                    for u in usernames:
                        if u.lower() in {r.lower() for r in REMOVED_USERS}:
                            continue
                        is_in_exp = any(eu.lower() == u.lower() for eu in expanded_users.keys())
                        if is_in_exp or get_user_info(u) is not None:
                            already_has_access.append(u)

                    if already_has_access:
                        access_str = ", ".join([f"@{u}" for u in already_has_access])
                        bot.editMessageText(message, f"<b>❌ Los usuarios</b> {access_str} <b>ya tienen acceso al bot.</b>", parse_mode='html')
                        return

                    is_plural_users = len(usernames) > 1
                    for u in usernames:
                        REMOVED_USERS = {r for r in REMOVED_USERS if r.lower() != u.lower()}
                        USER_CLOUD_OVERRIDES[u.lower()] = selected_cloud.copy()
                    
                    short_host = selected_cloud['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                    users_str = ", ".join([f"@{u}" for u in usernames])
                    
                    if is_plural_users:
                        msg_text = f"<b>✅ ¡Usuarios agregados con éxito!</b>\n\n👥 <b>Usuarios:</b> <b>{users_str}</b>\n☁️ <b>Nube asignada:</b> <code>{short_host}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>"
                    else:
                        msg_text = f"<b>✅ ¡Usuario agregado con éxito!</b>\n\n👤 <b>Usuario:</b> <b>{users_str}</b>\n☁️ <b>Nube asignada:</b> <code>{short_host}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>"
                    
                    bot.editMessageText(message, msg_text, parse_mode='html')
                    return
                except Exception as e:
                    bot.editMessageText(message, f"<b>❌ Formato incorrecto para /add.</b>\n💡 <b>Uso correcto:</b> <code>/add usuario1,usuario2 [número_de_nube (1-{len(AVAILABLE_CLOUDS)})]</code>", parse_mode='html')
                    return

            if msgText.lower().startswith('/remove'):
                parts = msgText.replace('/remove', '').strip()
                if not parts:
                    bot.editMessageText(message, "<b>❌ Formato incorrecto para /remove.</b>\n💡 <b>Uso correcto:</b> <code>/remove usuario1,usuario2</code>", parse_mode='html')
                    return
                try:
                    usernames = [u.strip().lstrip('@') for u in parts.split(',')]
                    usernames = [u for u in usernames if u]
                    if not usernames:
                        bot.editMessageText(message, "<b>❌ Especifica al menos un usuario válido.</b>\n💡 <b>Uso correcto:</b> /remove usuario1,usuario2", parse_mode='html')
                        return
                    if any(u.lower() == ADMIN_USERNAME.lower() for u in usernames):
                        bot.editMessageText(message, f"🛡️ <b>Acción denegada:</b> <b>No es posible quitar al usuario administrador (@{ADMIN_USERNAME}).</b>", parse_mode='html')
                        return
                    
                    removed_users = []
                    not_found_users = []
                    for u in usernames:
                        exists = False
                        is_in_exp = any(eu.lower() == u.lower() for eu in expanded_users.keys())
                        if is_in_exp or get_user_info(u) is not None:
                            exists = True
                            REMOVED_USERS.add(u.lower())
                            if u.lower() in {b.lower() for b in BANNED_USERS}:
                                BANNED_USERS = {b for b in BANNED_USERS if b.lower() != u.lower()}
                            if u.lower() in USER_CLOUD_OVERRIDES:
                                del USER_CLOUD_OVERRIDES[u.lower()]
                        if exists: removed_users.append(u)
                        else: not_found_users.append(u)
                    
                    is_plural = len(removed_users) > 1
                    users_str = ", ".join([f"@{u}" for u in removed_users])
                    response_text = ""
                    if removed_users:
                        if is_plural: response_text += f"<b>✅ ¡Usuarios eliminados con éxito!</b>\n\n👥 <b>Usuarios:</b> <b>{users_str}</b>"
                        else: response_text += f"<b>✅ ¡Usuario eliminado con éxito!</b>\n\n👤 <b>Usuario:</b> <b>{users_str}</b>"
                    if not_found_users:
                        nf_str = ", ".join([f"@{u}" for u in not_found_users])
                        response_text += f"\n\n⚠️ <b>No se encontraron en el sistema:</b> <b>{nf_str}</b>"
                    bot.editMessageText(message, response_text, parse_mode='html')
                    return
                except Exception as e:
                    bot.editMessageText(message, f"<b>❌ Error al quitar usuarios:</b> <b>{str(e)}</b>", parse_mode='html')
                    return

            if msgText.lower().startswith('/ban'):
                parts = msgText.replace('/ban', '').strip()
                if not parts:
                    bot.editMessageText(message, "<b>❌ Formato incorrecto para /ban.</b>\n💡 <b>Uso correcto:</b> <code>/ban usuario1,usuario2</code>", parse_mode='html')
                    return
                try:
                    targets = [u.strip().lstrip('@') for u in parts.split(',')]
                    targets = [u for u in targets if u]
                    if not targets:
                        bot.editMessageText(message, "<b>❌ Especifica al menos un usuario válido.</b>\n💡 <b>Uso correcto:</b> /ban usuario1,usuario2", parse_mode='html')
                        return
                    if any(t.lower() == ADMIN_USERNAME.lower() for t in targets):
                        bot.editMessageText(message, f'🛡️ <b>Acción denegada:</b> <b>No es posible banear al usuario administrador (@{ADMIN_USERNAME}).</b>', parse_mode='html')
                        return
                    
                    success_targets = []
                    already_banned = []
                    not_found = []
                    banned_lower = {b.lower() for b in BANNED_USERS}
                    for target in targets:
                        is_in_exp = any(eu.lower() == target.lower() for eu in expanded_users.keys()) and not any(r.lower() == target.lower() for r in REMOVED_USERS)
                        if not is_in_exp and get_user_info(target) is None:
                            not_found.append(target); continue
                        if target.lower() in banned_lower:
                            already_banned.append(target); continue
                        BANNED_USERS.add(target)
                        success_targets.append(target)
                    
                    is_plural = len(success_targets) > 1
                    targets_str = ", ".join([f"@{u}" for u in success_targets])
                    response_text = ""
                    if success_targets:
                        if is_plural: response_text += f"<b>🚫 ¡Usuarios baneados con éxito!</b>\n\n👥 <b>Usuarios:</b> <b>{targets_str}</b>"
                        else: response_text += f"<b>🚫 ¡Usuario baneado con éxito!</b>\n\n👤 <b>Usuario:</b> <b>{targets_str}</b>"
                    if already_banned:
                        ab_str = ", ".join([f"@{u}" for u in already_banned])
                        response_text += f"\n\nℹ️ <b>Ya se encontraban baneados:</b> <b>{ab_str}</b>"
                    if not_found:
                        nf_str = ", ".join([f"@{u}" for u in not_found])
                        response_text += f"\n\n❌ <b>No existen en el sistema:</b> <b>{nf_str}</b>"
                    bot.editMessageText(message, response_text, parse_mode='html')
                    return
                except Exception as e:
                    bot.editMessageText(message, f"<b>❌ Error al banear usuarios:</b> <b>{str(e)}</b>", parse_mode='html')
                    return

            if msgText.lower().startswith('/unban'):
                parts = msgText.replace('/unban', '').strip()
                if not parts:
                    bot.editMessageText(message, "<b>❌ Formato incorrecto para /unban.</b>\n💡 <b>Uso correcto:</b> <code>/unban usuario1,usuario2</code>", parse_mode='html')
                    return
                try:
                    targets = [u.strip().lstrip('@') for u in parts.split(',')]
                    targets = [u for u in targets if u]
                    if not targets:
                        bot.editMessageText(message, "<b>❌ Especifica al menos un usuario válido.</b>\n💡 <b>Uso correcto:</b> /unban usuario1,usuario2", parse_mode='html')
                        return
                    if any(t.lower() == ADMIN_USERNAME.lower() for t in targets):
                        bot.editMessageText(message, f'🛡️ <b>Acción denegada:</b> <b>El usuario administrador (@{ADMIN_USERNAME}) no puede ser objetivo de este comando.</b>', parse_mode='html')
                        return
                    
                    success_targets = []
                    not_banned = []
                    not_found = []
                    banned_lower = {b.lower() for b in BANNED_USERS}
                    for target in targets:
                        is_in_exp = any(eu.lower() == target.lower() for eu in expanded_users.keys())
                        if not is_in_exp and get_user_info(target) is None:
                            not_found.append(target); continue
                        if target.lower() not in banned_lower:
                            not_banned.append(target); continue
                        BANNED_USERS = {b for b in BANNED_USERS if b.lower() != target.lower()}
                        success_targets.append(target)
                    
                    is_plural = len(success_targets) > 1
                    targets_str = ", ".join([f"@{u}" for u in success_targets])
                    response_text = ""
                    if success_targets:
                        if is_plural: response_text += f"<b>✅ ¡Usuarios desbaneados con éxito!</b>\n\n👥 <b>Usuarios:</b> <b>{targets_str}</b>"
                        else: response_text += f"<b>✅ ¡Usuario desbaneado con éxito!</b>\n\n👤 <b>Usuario:</b> <b>{targets_str}</b>"
                    if not_banned:
                        nb_str = ", ".join([f"@{u}" for u in not_banned])
                        response_text += f"\n\nℹ️ <b>No estaban baneados:</b> <b>{nb_str}</b>"
                    if not_found:
                        nf_str = ", ".join([f"@{u}" for u in not_found])
                        response_text += f"\n\n❌ <b>No existen en el sistema:</b> <b>{nf_str}</b>"
                    bot.editMessageText(message, response_text, parse_mode='html')
                    return
                except Exception as e:
                    bot.editMessageText(message, f"<b>❌ Error al desbanear usuarios:</b> <b>{str(e)}</b>", parse_mode='html')
                    return

            if msgText.lower().startswith('/userfiles'):
                try:
                    parts = msgText.strip().split()
                    if len(parts) < 3:
                        guide_msg = (
                            "<b>❌ Formato incorrecto para /userfiles.</b>\n\n"
                            "💡 <b>Uso correcto:</b> <code>/userfiles @usuario [número_de_nube]</code>\n"
                            "<b>Ejemplo:</b> <code>/userfiles @Pedro 1</code>\n\n"
                            "ℹ️ <i>Usa /adm_userclouds para revisar los números de nubes disponibles.</i>"
                        )
                        bot.editMessageText(message, guide_msg, parse_mode='html')
                        return
                    
                    target_user = parts[1].strip().lstrip('@')
                    cloud_num_part = parts[2].strip()
                    
                    if not cloud_num_part.isdigit():
                        bot.editMessageText(message, "<b>❌ El número de nube debe ser un dígito válido.</b>\n💡 <b>Ejemplo:</b> /userfiles @Pedro 1", parse_mode='html')
                        return
                    
                    cloud_idx = int(cloud_num_part) - 1
                    if not (0 <= cloud_idx < len(AVAILABLE_CLOUDS)):
                        bot.editMessageText(message, f"<b>❌ Número de nube inválido.</b>\n💡 <b>Debe ser un valor del 1 al {len(AVAILABLE_CLOUDS)}.</b>", parse_mode='html')
                        return
                    
                    cloud_cfg = AVAILABLE_CLOUDS[cloud_idx]
                    short_host = cloud_cfg['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                    
                    bot.editMessageText(message, f"<b>🔍 Buscando evidencias de @{target_user} en <code>{short_host}</code>...</b>", parse_mode='html')
                    
                    proxy = ProxyCloud.parse(cloud_cfg['proxy']) if cloud_cfg.get('proxy') else None
                    client = MoodleClient(cloud_cfg['moodle_user'],
                                           cloud_cfg['moodle_password'],
                                           cloud_cfg['moodle_host'],
                                           cloud_cfg['moodle_repo_id'],
                                           proxy=proxy)
                    
                    if client.login():
                        all_evidences = client.getEvidences()
                        user_evidences = []
                        search_pattern = f"{USER_EVIDENCE_MARKER}{target_user}"
                        
                        for ev in all_evidences:
                            if ev['name'].endswith(search_pattern):
                                clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{target_user}", "")
                                file_count = len(ev.get('files', []))
                                user_evidences.append({
                                    'clean_name': clean_name,
                                    'file_count': file_count,
                                    'original': ev
                                })
                        
                        client.logout()
                        
                        if user_evidences:
                            files_msg = f"📁 <b>Evidencias de @{target_user}</b>\n☁️ <b>Nube:</b> <code>{short_host}</code>\n\n"
                            for idx, item in enumerate(user_evidences):
                                files_msg += f"<b>{idx}.</b> <b>{item['clean_name']}</b> [ <b>{item['file_count']} archivos</b> ]\n   🗑️ Borrar: /udel_{cloud_idx}_{target_user}_{idx}\n\n"
                            files_msg += f"<b>Total:</b> <b>{len(user_evidences)} evidencia(s)</b>\n\n"
                            files_msg += f"💣 <b>Borrar todas:</b> /udel_all_{cloud_idx}_{target_user}"
                            
                            send_long_message(bot, chat_id, files_msg, original_message=message, parse_mode='html')
                        else:
                            bot.editMessageText(message, f"<b>📭 @{target_user} no tiene evidencias en la nube <code>{short_host}</code>.</b>", parse_mode='html')
                    else:
                        bot.editMessageText(message, f"<b>❌ Error al conectar con la nube <code>{short_host}</code>.</b>", parse_mode='html')
                except Exception as e:
                    bot.editMessageText(message, f"<b>❌ Error:</b> <b>{str(e)}</b>", parse_mode='html')
                return

        if username.lower() == ADMIN_USERNAME.lower() and msgText.lower().startswith('/udel_all_'):
            try:
                parts = msgText.strip().split('_')
                if len(parts) >= 4:
                    cloud_idx = int(parts[2])
                    target_user = "_".join(parts[3:]).strip().lstrip('@')
                else:
                    bot.editMessageText(message, "<b>❌ Formato incorrecto.</b>", parse_mode='html')
                    return
                
                if not (0 <= cloud_idx < len(AVAILABLE_CLOUDS)) or not target_user:
                    bot.editMessageText(message, "<b>❌ Formato incorrecto.</b>", parse_mode='html')
                    return
                
                cloud_cfg = AVAILABLE_CLOUDS[cloud_idx]
                short_host = cloud_cfg['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                
                bot.editMessageText(message, f"<b>🗑️ Eliminando todas las evidencias de @{target_user} en <code>{short_host}</code>...</b>", parse_mode='html')
                
                proxy = ProxyCloud.parse(cloud_cfg['proxy']) if cloud_cfg.get('proxy') else None
                client = MoodleClient(cloud_cfg['moodle_user'],
                                       cloud_cfg['moodle_password'],
                                       cloud_cfg['moodle_host'],
                                       cloud_cfg['moodle_repo_id'],
                                       proxy=proxy)
                
                if client.login():
                    all_evidences = client.getEvidences()
                    user_evidences = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{target_user}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            user_evidences.append(ev)
                    
                    if not user_evidences:
                        bot.editMessageText(message, f"<b>📭 @{target_user} no tiene evidencias para eliminar en la nube <code>{short_host}</code>.</b>", parse_mode='html')
                        client.logout()
                        return
                    
                    total_evidences = len(user_evidences)
                    total_files = sum(len(ev.get('files', [])) for ev in user_evidences)
                    
                    for item in user_evidences:
                        try:
                            client.deleteEvidence(item)
                        except: pass
                    
                    client.logout()
                    
                    memory_stats.log_delete_all(
                        username=target_user,
                        deleted_evidences=total_evidences,
                        deleted_files=total_files,
                        moodle_host=cloud_cfg['moodle_host']
                    )

                    if LOG_GROUP_ID != 0:
                        try:
                            msg_log = (
                                f"<b>🗑️💥 ¡Eliminación masiva! (Admin)</b>\n\n"
                                f"👤 <b>Usuario afectado:</b> <b>@{target_user}</b>\n"
                                f"📊 <b>Evidencias borradas:</b> <b>{total_evidences}</b>\n"
                                f"📁 <b>Archivos borrados:</b> <b>{total_files}</b>\n"
                                f"☁️ <b>Nube:</b> <code>{short_host}</code>"
                            )
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar eliminación masiva de usuario al grupo: {e}")
                    
                    success_msg = f"<b>💥 ¡Eliminación masiva completada!</b>\n\n👤 <b>Usuario:</b> <b>@{target_user}</b>\n☁️ <b>Nube:</b> <code>{short_host}</code>\n📊 <b>Evidencias eliminadas:</b> <b>{total_evidences}</b>\n📁 <b>Archivos borrados:</b> <b>{total_files}</b>"
                    bot.editMessageText(message, success_msg, parse_mode='html')
                else:
                    bot.editMessageText(message, f"<b>❌ Error al conectar con la nube <code>{short_host}</code>.</b>", parse_mode='html')
            except Exception as e:
                bot.editMessageText(message, f"<b>❌ Error:</b> <b>{str(e)}</b>", parse_mode='html')
            return

        if username.lower() == ADMIN_USERNAME.lower() and msgText.startswith('/udel_'):
            try:
                parts = msgText.split('_')
                if len(parts) < 4:
                    bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /udel_0_usuario_0', parse_mode='html')
                    return
                
                cloud_idx = int(parts[1])
                ev_idx = int(parts[-1])
                target_user = "_".join(parts[2:-1]).strip().lstrip('@')
                
                if not (0 <= cloud_idx < len(AVAILABLE_CLOUDS)):
                    bot.editMessageText(message, '<b>❌ Índice de nube inválido.</b>', parse_mode='html')
                    return
                
                cloud_cfg = AVAILABLE_CLOUDS[cloud_idx]
                short_host = cloud_cfg['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                
                bot.editMessageText(message, f'<b>🗑️ Buscando evidencia de @{target_user} para eliminar...</b>', parse_mode='html')
                
                proxy = ProxyCloud.parse(cloud_cfg['proxy']) if cloud_cfg.get('proxy') else None
                client = MoodleClient(cloud_cfg['moodle_user'],
                                       cloud_cfg['moodle_password'],
                                       cloud_cfg['moodle_host'],
                                       cloud_cfg['moodle_repo_id'],
                                       proxy=proxy)
                
                if client.login():
                    all_evidences = client.getEvidences()
                    user_evidences = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{target_user}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{target_user}", "")
                            file_count = len(ev.get('files', []))
                            user_evidences.append({
                                'clean_name': clean_name,
                                'file_count': file_count,
                                'original': ev
                            })
                    
                    if ev_idx < 0 or ev_idx >= len(user_evidences):
                        bot.editMessageText(message, '<b>❌ Índice de evidencia inválido.</b>', parse_mode='html')
                        client.logout()
                        return
                    
                    target_ev_item = user_evidences[ev_idx]
                    evfile = target_ev_item['original']
                    evidence_clean_name = target_ev_item['clean_name']
                    file_count = target_ev_item['file_count']
                    
                    client.deleteEvidence(evfile)
                    
                    all_evidences = client.getEvidences()
                    updated_user_evidences = []
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{target_user}", "")
                            updated_user_evidences.append({
                                'clean_name': clean_name,
                                'file_count': len(ev.get('files', [])),
                                'original': ev
                            })
                    
                    client.logout()
                    
                    memory_stats.log_delete(
                        username=target_user,
                        filename=f"{evidence_clean_name} ({file_count} archivos) [Borrado por Admin]",
                        evidence_name=evidence_clean_name,
                        moodle_host=cloud_cfg['moodle_host']
                    )

                    if LOG_GROUP_ID != 0:
                        try:
                            msg_log = (
                                f"<b>🗑️ ¡Eliminación de evidencia! (Admin)</b>\n\n"
                                f"👤 <b>Usuario afectado:</b> <b>@{target_user}</b>\n"
                                f"📄 <b>Evidencia:</b> <b>{evidence_clean_name}</b>\n"
                                f"📁 <b>Archivos eliminados:</b> <b>{file_count}</b>\n"
                                f"☁️ <b>Nube:</b> <code>{short_host}</code>"
                            )
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar eliminación de admin al grupo: {e}")
                    
                    confirmation_msg = f"🗑️ <b>Evidencia de @{target_user} eliminada</b>\n\n• <b>Evidencia:</b> <b>{evidence_clean_name}</b>\n• <b>Archivos borrados:</b> <b>{file_count}</b>\n• <b>Nube:</b> <code>{short_host}</code>\n\n"
                    
                    if updated_user_evidences:
                        confirmation_msg += f"📋 <b>Evidencias restantes de @{target_user}:</b>\n\n"
                        for idx, item in enumerate(updated_user_evidences):
                            confirmation_msg += f"<b>{idx}.</b> <b>{item['clean_name']}</b> [ <b>{item['file_count']} archivos</b> ]\n   🗑️ Borrar: /udel_{cloud_idx}_{target_user}_{idx}\n\n"
                        confirmation_msg += f"💣 <b>Borrar todas:</b> /udel_all_{cloud_idx}_{target_user}"
                    else:
                        confirmation_msg += f"<b>📭 @{target_user} ya no tiene más evidencias en esta nube.</b>"
                    
                    bot.editMessageText(message, confirmation_msg, parse_mode='html')
                else:
                    bot.editMessageText(message, f'<b>❌ Error al conectar con la nube <code>{short_host}</code>.</b>', parse_mode='html')
            except Exception as e:
                bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
            return

        if username in CHANGING_CLOUD_USERS:
            if msgText.strip().isdigit():
                num = int(msgText.strip())
                if 1 <= num <= len(AVAILABLE_CLOUDS):
                    selected_cloud = AVAILABLE_CLOUDS[num - 1]
                    short_name = selected_cloud['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                    old_host = user_info.get('moodle_host', '').replace('https://', '').replace('http://', '').strip('/')
                    
                    if user_info.get('moodle_host') == selected_cloud['moodle_host']:
                        CHANGING_CLOUD_USERS.discard(username)
                        bot.editMessageText(message, f"ℹ️ <b>Ya estás usando esta nube</b>\n\n☁️ <b>Nube actual:</b> <code>{short_name}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>", parse_mode='html')
                        return
                    
                    USER_CLOUD_OVERRIDES[username.lower()] = selected_cloud.copy()
                    CHANGING_CLOUD_USERS.discard(username)
                    
                    bot.editMessageText(message, f"<b>✅ ¡Nube cambiada exitosamente!</b>\n\n☁️ <b>Nueva nube:</b> <code>{short_name}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>", parse_mode='html')
                    
                    if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                        try:
                            msg_log = (f"<b>☁️ ¡Cambio de nube!</b>\n\n"
                                       f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                       f"<b>🔄 Anterior:</b> <code>{old_host}</code>\n"
                                       f"<b>🆕 Nueva:</b> <code>{short_name}</code>\n"
                                       f"<b>⚖️ Límite:</b> <b>{selected_cloud['zips']} MB</b>")
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar cambio de nube al grupo: {e}")
                    return
                else:
                    bot.editMessageText(message, f"<b>❌ Número inválido. Envía un número del 1 al {len(AVAILABLE_CLOUDS)}.</b>", parse_mode='html')
                    CHANGING_CLOUD_USERS.discard(username)
                    return
            else:
                CHANGING_CLOUD_USERS.discard(username)

        if '/cambiar' in msgText:
            clean_cmd = msgText.replace('/cambiar_', ' ').replace('/cambiar', ' ').strip()
            if clean_cmd.isdigit():
                num = int(clean_cmd)
                if 1 <= num <= len(AVAILABLE_CLOUDS):
                    selected_cloud = AVAILABLE_CLOUDS[num - 1]
                    short_name = selected_cloud['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                    old_host = user_info.get('moodle_host', '').replace('https://', '').replace('http://', '').strip('/')
                    
                    if user_info.get('moodle_host') == selected_cloud['moodle_host']:
                        bot.editMessageText(message, f"ℹ️ <b>Ya estás usando esta nube</b>\n\n☁️ <b>Nube actual:</b> <code>{short_name}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>", parse_mode='html')
                        return
                    
                    USER_CLOUD_OVERRIDES[username.lower()] = selected_cloud.copy()
                    bot.editMessageText(message, f"<b>✅ ¡Nube cambiada exitosamente!</b>\n\n☁️ <b>Nueva nube:</b> <code>{short_name}</code>\n⚖️ <b>Límite:</b> <b>{selected_cloud['zips']} MB</b>", parse_mode='html')
                    
                    if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                        try:
                            msg_log = (f"<b>☁️ ¡Cambio de nube!</b>\n\n"
                                       f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                       f"<b>🔄 Anterior:</b> <code>{old_host}</code>\n"
                                       f"<b>🆕 Nueva:</b> <code>{short_name}</code>\n"
                                       f"<b>⚖️ Límite:</b> <b>{selected_cloud['zips']} MB</b>")
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar cambio de nube al grupo: {e}")
                    return
            
            menu_msg = "☁️ <b>Selecciona tu nueva nube</b>\n\n"
            for i, c in enumerate(AVAILABLE_CLOUDS, 1):
                short = c['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                menu_msg += f"<b>{i}.</b> <code>{short}</code>\n   ⚖️ <b>Límite:</b> <b>{c['zips']} MB</b>\n\n"
            menu_msg += f"💡 <b>Envía solo el número</b> (1 al {len(AVAILABLE_CLOUDS)})."
            
            CHANGING_CLOUD_USERS.add(username)
            bot.editMessageText(message, menu_msg, parse_mode='html')
            return

        if '/start' in msgText:
            if username.lower() == ADMIN_USERNAME.lower():
                admin_current_cloud = user_info["moodle_host"].replace('https://', '').replace('http://', '').strip('/')
                start_msg = f"""
👑 <b>Usuario Administrador</b>

👤 <b>Usuario:</b> <b>@{username}</b>
☁️ <b>Nube actual:</b> <code>{admin_current_cloud}</code>
⚖️ <b>Límite:</b> <b>{user_info["zips"]} MB</b>
🔧 <b>Rol:</b> <b>Administrador</b>

⚠️ <b>Nota importante:</b>
• <b>Acceso total a todas las nubes</b>
• <b>Gestión de evidencias globales</b>

🎯 <b>Comandos principales:</b>
/admin - <b>Panel de administración</b>
/status - <b>Estado de las nubes 🟢/🔴</b>
/procesos - <b>Procesos en tiempo real 🚀</b>
/mantenimiento - <b>Modo mantenimiento 🛠️</b>
/add - <b>Agregar usuario y nube ➕</b>
/remove - <b>Quitar usuario del bot ➖</b>
/ban - <b>Banear usuario 🚫</b>
/unban - <b>Desbanear usuario ✅</b>
/userfiles @usuario [nube] - <b>Ver y borrar evidencias de un usuario 📁</b>

📈 <b>Estadísticas y gestión:</b>
/adm_logs - <b>Logs del sistema</b>
/adm_users - <b>Estadísticas por usuario</b>
/adm_userclouds - <b>Ver nubes y usuarios</b>
/adm_uploads - <b>Últimas subidas</b>
/adm_deletes - <b>Últimas eliminaciones</b>
/adm_cleardata - <b>Limpiar estadísticas</b>
/adm_colas - <b>Ver colas de todos los usuarios 🚦</b>

☁️ <b>Gestión de nubes:</b>
/adm_allclouds - <b>Ver todas las nubes</b>
/adm_cloud_X - <b>Nube específica</b>
/adm_show_X_Y - <b>Detalles de evidencia</b>
/adm_fetch_X_Y - <b>Descargar TXT</b>
/adm_delete_X_Y - <b>Eliminar evidencia</b>
/adm_wipe_X - <b>Limpiar nube X</b>
/adm_nuke - <b>Eliminación masiva ⚠️</b>

🔧 <b>Tus comandos personales:</b>
/cambiar - <b>Cambiar de nube (1 al {len(AVAILABLE_CLOUDS)}) 🔄</b>
/files - <b>Ver tus evidencias</b>
/txt_X - <b>Ver TXT de tu evidencia</b>
/del_X - <b>Eliminar tu evidencia</b>
/delall - <b>Eliminar tus evidencias</b>
/mystats - <b>Tus estadísticas</b>
/cola - <b>Ver tu cola de descargas 🚦</b>
                """
            else:
                current_cloud_short = user_info["moodle_host"].replace('https://', '').replace('http://', '').strip('/')
                start_msg = f"""
👤 <b>Usuario Regular</b>

👤 <b>Usuario:</b> <b>@{username}</b>
☁️ <b>Nube actual:</b> <code>{current_cloud_short}</code>
⚖️ <b>Límite:</b> <b>{user_info["zips"]} MB</b>
📁 <b>Evidence:</b> <b>Activado</b>

🔧 <b>Tus comandos:</b>
/start - <b>Ver esta información</b>
/cambiar - <b>Cambiar de nube (1 al {len(AVAILABLE_CLOUDS)}) 🔄</b>
/status - <b>Estado de tu nube 🟢/🔴</b>
/files - <b>Ver tus evidencias</b>
/txt_X - <b>Ver TXT de evidencia X</b>
/del_X - <b>Eliminar evidencia X</b>
/delall - <b>Eliminar tus evidencias</b>
/mystats - <b>Ver tus estadísticas</b>
/cola - <b>Ver tu cola de descargas 🚦</b>
                """
            
            bot.editMessageText(message, start_msg, parse_mode='html')
            send_sticker(chat_id, "CAACAgEAAxkBAAIoVGqA9obyhoMJe62uOFPzvoFk6vwpAAK7BgACnFgJRDiBixe0VxapPQQ")
            return

        if '/status' == msgText:
            if username in ACTIVE_STATUS_CHECKS:
                bot.editMessageText(message, "<b>⏳ Ya hay una verificación de estado en curso. Por favor, espera a que termine.</b>", parse_mode='html')
                return
            
            ACTIVE_STATUS_CHECKS.add(username)
            try:
                if username.lower() == ADMIN_USERNAME.lower():
                    bot.editMessageText(message, "<b>🔍 Verificando nubes una a una...</b>", parse_mode='html')
                    unique_configs = []
                    checked_hosts = set()
                    for cfg in AVAILABLE_CLOUDS:
                        moodle_host = cfg.get('moodle_host', '')
                        if moodle_host in checked_hosts:
                            continue
                        checked_hosts.add(moodle_host)
                        unique_configs.append(cfg)
                    
                    total_clouds = len(unique_configs)
                    for idx, cfg in enumerate(unique_configs):
                        s = check_single_cloud(cfg)
                        icon = "🟢 En línea" if s['online'] else "🔴 Fuera de línea"
                        clean_url = s['url'].replace('https://', '').replace('http://', '').strip('/')
                        status_msg = f"☁️ <code>{clean_url}</code>\n<b>Estado:</b> <b>{icon}</b>"
                        
                        if idx == 0:
                            bot.editMessageText(message, status_msg, parse_mode='html')
                        else:
                            time.sleep(0.4)
                            bot.sendMessage(chat_id, status_msg, parse_mode='html')
                else:
                    bot.editMessageText(message, "<b>🔍 Verificando estado de tu nube...</b>", parse_mode='html')
                    s = check_single_cloud(user_info)
                    icon = "🟢 En línea" if s['online'] else "🔴 Fuera de línea"
                    clean_url = user_info["moodle_host"].replace('https://', '').replace('http://', '').strip('/')
                    status_msg = f"☁️ <code>{clean_url}</code>\n<b>Estado:</b> <b>{icon}</b>"
                    bot.editMessageText(message, status_msg, parse_mode='html')
            except Exception as e:
                bot.editMessageText(message, f"<b>❌ Error al comprobar el estado de la nube:</b> <b>{str(e)}</b>", parse_mode='html')
            finally:
                ACTIVE_STATUS_CHECKS.discard(username)
            return

        if username.lower() == ADMIN_USERNAME.lower():
            if msgText.startswith('/mantenimiento'):
                if 'on' in msgText.lower():
                    MAINTENANCE_MODE = True
                elif 'off' in msgText.lower():
                    MAINTENANCE_MODE = False
                else:
                    MAINTENANCE_MODE = not MAINTENANCE_MODE
                
                estado = "ACTIVADO 🔴" if MAINTENANCE_MODE else "DESACTIVADO 🟢"
                
                cancel_count = 0
                pending_count = 0
                if MAINTENANCE_MODE:
                    active_dict, pending_dict = queue_manager.get_full_snapshot()
                    
                    for uname, active_task in active_dict.items():
                        if not active_task or uname.lower() == ADMIN_USERNAME.lower():
                            continue
                        try:
                            if active_task.thread_ctx:
                                active_task.thread_ctx.store('stop', True)
                                active_task.thread_ctx.store('cancelled', True)
                                dl = active_task.thread_ctx.getStore('downloader')
                                if dl:
                                    try: dl.stop()
                                    except: pass
                                msg_obj = active_task.thread_ctx.getStore('msg')
                                if msg_obj:
                                    try:
                                        bot.editMessageText(msg_obj, '<b>⚠️ Tarea cancelada automáticamente por mantenimiento.</b>', parse_mode='html')
                                    except: pass
                            clean_process(active_task.task_id)
                            cancel_count += 1
                        except: pass
                    
                    for uname, dq in pending_dict.items():
                        if uname.lower() == ADMIN_USERNAME.lower():
                            continue
                        for t in dq:
                            try:
                                queue_manager.cancel(uname, t.task_id)
                                clean_process(t.task_id)
                                bot.sendMessage(t.chat_id, f'<b>⚠️ Enlace en espera cancelado por mantenimiento.</b>\n\n📄 <b>{t.filename}</b>', parse_mode='html')
                                pending_count += 1
                            except: pass
                    
                    for tid, p in list(ACTIVE_PROCESSES.items()):
                        if p.get('user', '').lower() != ADMIN_USERNAME.lower():
                            clean_process(tid)
                
                try:
                    bot.deleteMessage(chat_id, message.message_id)
                except:
                    pass

                aviso_cancelados = ""
                if MAINTENANCE_MODE and (cancel_count > 0 or pending_count > 0):
                    aviso_cancelados = f"\n\n⚠️ <b>Procesos afectados:</b>\n• Activos cancelados: <b>{cancel_count}</b>\n• En cola cancelados: <b>{pending_count}</b>"
                
                admin_maint_msg = f"<b>🛠️ Modo mantenimiento:</b> <b>{estado}</b>{aviso_cancelados}"

                if LOG_GROUP_ID != 0:
                    try:
                        if MAINTENANCE_MODE:
                            msg_maint = (f"<b>🛠️ ¡Modo mantenimiento ACTIVADO!</b>\n\n"
                                         f"⚠️ <b>Se cancelaron {cancel_count} proceso(s) activo(s) y {pending_count} enlace(s) en cola.</b>")
                        else:
                            msg_maint = "<b>🛠️ ¡Modo mantenimiento DESACTIVADO! El bot opera con normalidad.</b>"
                        bot.sendMessage(LOG_GROUP_ID, msg_maint, parse_mode='html')
                        bot.sendMessage(ADMIN_CHAT_ID, msg_maint, parse_mode='html')
                    except Exception as e:
                        print(f"Error al notificar mantenimiento: {e}")
                
                bot.sendMessage(chat_id, admin_maint_msg, parse_mode='html')
                return
                
            elif msgText == '/procesos':
                if not ACTIVE_PROCESSES:
                    bot.editMessageText(message, "<b>✅ No hay procesos activos en este momento.</b>", parse_mode='html')
                    return
                
                proc_msg = "🔄 <b>Procesos activos en tiempo real</b>\n\n"
                procesos_borrar = []
                
                for tid, p in ACTIVE_PROCESSES.items():
                    tiempo_activo = int(time.time() - p['last_update'])
                    stalled_warning = " ⚠️ <b>(Posiblemente trabado)</b>" if tiempo_activo > 30 and ('📥 Descargando' in p['action'] or '⬆️ Preparando' in p['action']) else ""
                    
                    if tiempo_activo > 60:
                        procesos_borrar.append(tid)
                        continue
                    
                    proc_msg += f"👤 <b>Usuario:</b> <b>@{p['user']}</b>\n"
                    proc_msg += f"🛠️ <b>Acción:</b> <b>{p['action']}</b>{stalled_warning}\n"
                    proc_msg += f"📄 <b>Nombre:</b> <b>{p['file']}</b>\n"
                    if '🗜️ Comprimiendo' not in p['action'] and '⬆️ Preparando' not in p['action']:
                        proc_msg += f"📊 <b>Progreso:</b> <b>{p['percent']}</b>\n"
                    proc_msg += f"\n"
                
                for tid in procesos_borrar:
                    clean_process(tid)
                
                if len(ACTIVE_PROCESSES) == 0:
                    bot.editMessageText(message, "<b>✅ No hay procesos activos en este momento.</b>", parse_mode='html')
                else:
                    bot.editMessageText(message, proc_msg, parse_mode="html")
                return

        if username.lower() == ADMIN_USERNAME.lower():
            if msgText == '/admin':
                stats = memory_stats.get_all_stats()
                total_size_formatted = format_file_size(stats['total_size_uploaded'])
                current_date = format_cuba_date()
                
                if memory_stats.has_any_data():
                    admin_msg = f"""
👑 <b>Panel de administrador</b>
📅 <b>Fecha:</b> <b>{current_date}</b>

📊 <b>Estadísticas globales:</b>
• <b>Subidas totales:</b> <b>{stats['total_uploads']}</b>
• <b>Eliminaciones totales:</b> <b>{stats['total_deletes']}</b>
• <b>Espacio total subido:</b> <b>{total_size_formatted}</b>
• <b>Nubes configuradas:</b> <b>{len(AVAILABLE_CLOUDS)}</b>

🚀 <b>Comandos rápidos:</b>
/status - <b>Estado de las nubes 🟢/🔴</b>
/procesos - <b>Procesos activos 🚀</b>
/mantenimiento - <b>Activar/Desactivar 🛠️</b>
/add - <b>Agregar usuario y nube ➕</b>
/remove - <b>Quitar usuario del bot ➖</b>
/ban - <b>Banear usuario 🚫</b>
/unban - <b>Desbanear usuario ✅</b>
/userfiles @usuario [nube] - <b>Ver evidencias de usuario 📁</b>

📈 <b>Estadísticas y usuarios:</b>
/adm_logs - <b>Ver últimos logs</b>
/adm_users - <b>Estadísticas por usuario</b>
/adm_userclouds - <b>Ver nubes y usuarios</b>
/adm_uploads - <b>Últimas subidas</b>
/adm_deletes - <b>Últimas eliminaciones</b>
/adm_cleardata - <b>Limpiar todos los datos</b>
/adm_colas - <b>Ver colas de todos los usuarios 🚦</b>

☁️ <b>Gestión de nubes:</b>
/adm_allclouds - <b>Ver todas las nubes</b>
/adm_cloud_X - <b>Nube específica</b>
/adm_show_X_Y - <b>Detalles de evidencia</b>
/adm_fetch_X_Y - <b>Descargar TXT</b>
/adm_delete_X_Y - <b>Eliminar evidencia</b>
/adm_wipe_X - <b>Limpiar nube X</b>
/adm_nuke - <b>Eliminación masiva ⚠️</b>

🔧 <b>Otros:</b>
/start - <b>Información de usuario</b>

🕐 <b>Hora Cuba:</b> <b>{format_cuba_datetime()}</b>
                    """
                else:
                    admin_msg = f"""
👑 <b>Panel de administrador</b>
📅 <b>Fecha:</b> <b>{current_date}</b>

⚠️ <b>No hay datos registrados</b>
<b>Aún no se ha realizado ninguna acción en el bot.</b>

📊 <b>Nubes configuradas:</b> <b>{len(AVAILABLE_CLOUDS)}</b>

🚀 <b>Comandos rápidos:</b>
/status - <b>Estado de las nubes 🟢/🔴</b>
/procesos - <b>Procesos activos 🚀</b>
/mantenimiento - <b>Activar/Desactivar 🛠️</b>
/add - <b>Agregar usuario y nube ➕</b>
/remove - <b>Quitar usuario del bot ➖</b>
/ban - <b>Banear usuario 🚫</b>
/unban - <b>Desbanear usuario ✅</b>
/userfiles @usuario [nube] - <b>Ver evidencias de usuario 📁</b>

📈 <b>Estadísticas y usuarios:</b>
/adm_logs - <b>Ver últimos logs</b>
/adm_users - <b>Estadísticas por usuario</b>
/adm_userclouds - <b>Ver nubes y usuarios</b>
/adm_uploads - <b>Últimas subidas</b>
/adm_deletes - <b>Últimas eliminaciones</b>
/adm_colas - <b>Ver colas de todos los usuarios 🚦</b>

☁️ <b>Gestión de nubes:</b>
/adm_allclouds - <b>Ver todas las nubes</b>
/adm_cloud_X - <b>Ver nube específica</b>
/adm_show_X_Y - <b>Detalles de evidencia</b>
/adm_fetch_X_Y - <b>Descargar TXT</b>

🔧 <b>Otros:</b>
/start - <b>Información de usuario</b>

🕐 <b>Hora Cuba:</b> <b>{format_cuba_datetime()}</b>
                    """
                
                bot.editMessageText(message, admin_msg, parse_mode='html')
                return
            
            elif '/adm_' in msgText:
                if msgText == '/adm_colas':
                    try:
                        active_dict, pending_dict = queue_manager.get_full_snapshot()
                        all_users = {u for u in (set(active_dict.keys()) | set(pending_dict.keys()))
                                     if active_dict.get(u) or pending_dict.get(u)}

                        if not all_users:
                            bot.editMessageText(message, "<b>✅ No hay colas activas en este momento. Todo despejado.</b>", parse_mode='html')
                            return

                        colas_msg = "🚦 <b>Panel de colas — todos los usuarios</b>\n\n"
                        for u in sorted(all_users):
                            active_task = active_dict.get(u)
                            dq = pending_dict.get(u, [])
                            colas_msg += f"👤 <b>@{u}</b>\n"
                            if active_task:
                                colas_msg += f"   ▶️ <b>En curso:</b> <b>{active_task.filename}</b>\n   🗑️ /cancel_{active_task.task_id}\n"
                            if dq:
                                colas_msg += f"   ⏳ <b>En espera ({len(dq)}):</b>\n"
                                for idx, t in enumerate(dq, 1):
                                    colas_msg += f"      <b>{idx}.</b> {t.filename}  🗑️ /cancel_{t.task_id}\n"
                            colas_msg += "\n"

                        send_long_message(bot, chat_id, colas_msg, original_message=message, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener colas:</b> <b>{str(e)}</b>', parse_mode='html')
                    return

                if msgText == '/adm_userclouds':
                    try:
                        uclouds_msg = "☁️ <b>Gestión de nubes y usuarios</b>\n\n"
                        
                        for idx, cloud_cfg in enumerate(AVAILABLE_CLOUDS, 1):
                            target_host = cloud_cfg.get('moodle_host', '')
                            zips = cloud_cfg.get('zips', '?')
                            short = target_host.replace('https://', '').replace('http://', '').strip('/')
                            
                            assigned_users = []
                            for u in expanded_users.keys():
                                if u in REMOVED_USERS:
                                    continue
                                u_info = get_user_info(u)
                                current_host = u_info.get('moodle_host', '') if u_info else cloud_cfg.get('moodle_host', '')
                                if current_host == target_host:
                                    assigned_users.append(f"@{u.lstrip('@')}")
                            
                            users_str = ", ".join(assigned_users) if assigned_users else "Ninguno"
                            
                            uclouds_msg += f"🌐 <b>Nube {idx}:</b> <code>{short}</code>\n"
                            uclouds_msg += f"⚖️ <b>Límite:</b> <b>{zips} MB</b>\n"
                            uclouds_msg += f"👤 <b>Usuarios:</b> <b>{users_str}</b>\n\n"
                        
                        send_long_message(bot, chat_id, uclouds_msg, original_message=message, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener nubes y usuarios:</b> <b>{str(e)}</b>', parse_mode='html')
                    return

                elif '/adm_allclouds' in msgText:
                    try:
                        show_loading_progress(bot, message, 1, 3)
                        total_evidences = admin_evidence_manager.refresh_data()
                        show_loading_progress(bot, message, 2, 3)
                        
                        if total_evidences == 0:
                            empty_msg = f"""
<b>👑 Todas las nubes</b>
📊 <b>Resumen general:</b>
• <b>Nubes configuradas:</b> <b>{len(AVAILABLE_CLOUDS)}</b>
• <b>Evidencias totales:</b> <b>0</b>
• <b>Archivos totales:</b> <b>0</b>

<b>✅ Todas las nubes están vacías</b>
                            """
                            bot.editMessageText(message, empty_msg, parse_mode='html')
                            return
                        
                        total_clouds = len(admin_evidence_manager.clouds_dict)
                        total_files = 0
                        
                        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                            for ev in evidences:
                                total_files += ev['files_count']
                        
                        menu_msg = f"""
👑 <b>Gestión de todas las nubes</b>
📊 <b>Resumen general:</b>
• <b>Nubes:</b> <b>{total_clouds}</b>
• <b>Evidencias totales:</b> <b>{total_evidences}</b>
• <b>Archivos totales:</b> <b>{total_files}</b>

📋 <b>Nubes disponibles:</b>"""
                        
                        cloud_index = 0
                        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                            cloud_files = sum(ev['files_count'] for ev in evidences)
                            short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                            
                            menu_msg += f"\n\n<b>{cloud_index}.</b> <code>{short_name}</code>"
                            menu_msg += f"\n   📁 <b>{len(evidences)} evidencias, {cloud_files} archivos</b>"
                            menu_msg += f"\n   🔍 /adm_cloud_{cloud_index}"
                            
                            if len(evidences) > 0:
                                menu_msg += f"\n   🗑️ /adm_wipe_{cloud_index}"
                            
                            cloud_index += 1
                        
                        show_loading_progress(bot, message, 3, 3)
                        
                        if total_evidences > 0:
                            menu_msg += f"""

🔧 <b>OPCIONES MASIVAS:</b>
/adm_nuke - ⚠️ <b>Eliminación masiva</b>

ℹ️ <b>Usa</b> /adm_cloud_X <b>para ver evidencias</b>
                            """
                        else:
                            menu_msg += f"""

<b>✅ Todas las nubes están vacías</b>
                            """
                        
                        bot.editMessageText(message, menu_msg, parse_mode='html')
                        
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_cloud_' in msgText:
                    try:
                        cloud_idx = extract_one_param_simple(msgText, '/adm_cloud_')
                        if cloud_idx is None:
                            bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /adm_cloud_0', parse_mode='html')
                            return
                        
                        admin_evidence_manager.refresh_data()
                        
                        if cloud_idx < 0 or cloud_idx >= len(admin_evidence_manager.clouds_dict):
                            bot.editMessageText(message, f'<b>❌ Índice inválido. Máximo:</b> <b>{len(admin_evidence_manager.clouds_dict)-1}</b>', parse_mode='html')
                            return
                        
                        cloud_name = list(admin_evidence_manager.clouds_dict.keys())[cloud_idx]
                        evidences = admin_evidence_manager.clouds_dict[cloud_name]
                        short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                        
                        if not evidences:
                            empty_msg = f"""
<b>📭 NUBE VACÍA</b>
☁️ <code>{short_name}</code>
📊 <b>No hay evidencias en esta nube.</b>
                            """
                            bot.editMessageText(message, empty_msg, parse_mode='html')
                            return
                        
                        list_msg = f"""
<b>📋 EVIDENCIAS DE LA NUBE</b>
☁️ <code>{short_name}</code>

"""
                        for idx, evidence in enumerate(evidences):
                            ev_name = evidence['evidence_name']
                            clean_name = ev_name
                            user_tags = []
                            
                            for user in evidence['group_users']:
                                marker = f"{USER_EVIDENCE_MARKER}{user}"
                                if marker in ev_name:
                                    clean_name = ev_name.replace(marker, "").strip()
                                    user_tags.append(f"@{user}")
                            
                            if user_tags:
                                user_str = f" ({', '.join(user_tags[:2])})"
                                if len(user_tags) > 2:
                                    user_str = f" ({', '.join(user_tags[:2])}...)"
                            else:
                                user_str = ""
                            
                            list_msg += f"<b>{idx}.</b> <b>{clean_name[:35]}</b>"
                            if len(clean_name) > 35:
                                list_msg += "..."
                            list_msg += f"<b>{user_str}</b>\n"
                            list_msg += f"   📁 <b>Archivos:</b> <b>{evidence['files_count']}</b>\n"
                            list_msg += f"   👁️ <b>Ver:</b> /adm_show_{cloud_idx}_{idx}\n"
                            list_msg += f"   📄 <b>TXT:</b> /adm_fetch_{cloud_idx}_{idx}\n"
                            list_msg += f"   🗑️ <b>Borrar:</b> /adm_delete_{cloud_idx}_{idx}\n\n"
                        
                        total_evidences = len(evidences)
                        total_files = sum(e['files_count'] for e in evidences)
                        
                        list_msg += f"""
🔧 <b>ACCIÓN MASIVA:</b>
/adm_wipe_{cloud_idx} - <b>Eliminación masiva</b>

📊 <b>RESUMEN:</b>
• <b>Evidencias:</b> <b>{total_evidences}</b>
• <b>Archivos:</b> <b>{total_files}</b>
                        """
                        
                        send_long_message(bot, message.chat.id, list_msg, original_message=message, parse_mode='html')
                        
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_show_' in msgText:
                    try:
                        params = extract_two_params_simple(msgText, '/adm_show_')
                        if params is None:
                            bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /adm_show_0_1', parse_mode='html')
                            return
                        
                        cloud_idx, evid_idx = params
                        evidence = admin_evidence_manager.get_evidence(cloud_idx, evid_idx)
                        if evidence:
                            ev_name = evidence['evidence_name']
                            cloud_name = evidence['cloud_name']
                            short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                            
                            clean_name = ev_name
                            for user in evidence['group_users']:
                                marker = f"{USER_EVIDENCE_MARKER}{user}"
                                if marker in ev_name:
                                    clean_name = ev_name.replace(marker, "").strip()
                                    break
                            
                            show_msg = f"""
<b>👁️ Detalles de evidencia</b>
📝 <b>Nombre:</b> <b>{clean_name}</b>
📁 <b>Archivos:</b> <b>{evidence['files_count']}</b>
☁️ <b>Nube:</b> <code>{short_name}</code>

🔧 <b>ACCIONES:</b>
📄 /adm_fetch_{cloud_idx}_{evid_idx} - <b>TXT</b>
🗑️ /adm_delete_{cloud_idx}_{evid_idx} - <b>Eliminar</b>
                            """
                            bot.editMessageText(message, show_msg, parse_mode='html')
                        else:
                            bot.editMessageText(message, '<b>❌ No se encontró la evidencia</b>', parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_fetch_' in msgText:
                    try:
                        params = extract_two_params_simple(msgText, '/adm_fetch_')
                        if params is None:
                            bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /adm_fetch_0_1', parse_mode='html')
                            return
                        
                        cloud_idx, evid_idx = params
                        bot.editMessageText(message, '<b>📄 Obteniendo archivo TXT...</b>', parse_mode='html')
                        files = admin_evidence_manager.get_txt_for_evidence(cloud_idx, evid_idx)
                        
                        if files:
                            evidence = admin_evidence_manager.get_evidence(cloud_idx, evid_idx)
                            if evidence:
                                ev_name = evidence['evidence_name']
                                clean_name = ev_name
                                for user in evidence['group_users']:
                                    marker = f"{USER_EVIDENCE_MARKER}{user}"
                                    if marker in ev_name:
                                        clean_name = ev_name.replace(marker, "").strip()
                                        break
                                
                                safe_name = ''.join(c for c in clean_name if c.isalnum() or c in (' ', '-', '_')).strip()
                                if not safe_name:
                                    safe_name = f"evidencia_{cloud_idx}_{evid_idx}"
                                
                                txtname = f"{safe_name}.txt"
                                txt = open(txtname, 'w')
                                for i, f in enumerate(files):
                                    url = f['directurl']
                                    txt.write(url)
                                    if i < len(files) - 1:
                                        txt.write('\n\n')
                                txt.close()
                                bot.sendFile(chat_id, txtname)
                                os.unlink(txtname)
                                bot.editMessageText(message, f'<b>✅ TXT enviado:</b> <b>{clean_name[:50]}</b>', parse_mode='html')
                            else:
                                bot.editMessageText(message, '<b>❌ No se encontró la evidencia</b>', parse_mode='html')
                        else:
                            bot.editMessageText(message, '<b>❌ No hay archivos en esta evidencia</b>', parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_delete_' in msgText:
                    try:
                        params = extract_two_params_simple(msgText, '/adm_delete_')
                        if params is None:
                            bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /adm_delete_0_1', parse_mode='html')
                            return
                        
                        cloud_idx, evid_idx = params
                        bot.editMessageText(message, '<b>🔍 Verificando datos...</b>', parse_mode='html')
                        
                        admin_evidence_manager.refresh_data()
                        cloud_names = list(admin_evidence_manager.clouds_dict.keys())
                        
                        if cloud_idx < 0 or cloud_idx >= len(cloud_names):
                            bot.editMessageText(message, '<b>❌ Índice de nube inválido</b>', parse_mode='html')
                            show_updated_all_clouds(bot, message)
                            return
                        
                        cloud_name = cloud_names[cloud_idx]
                        evidences = admin_evidence_manager.clouds_dict.get(cloud_name, [])
                        
                        if not evidences:
                            bot.editMessageText(message, f'<b>📭 La nube {cloud_idx} ya está vacía</b>', parse_mode='html')
                            show_updated_all_clouds(bot, message)
                            return
                        
                        if evid_idx < 0 or evid_idx >= len(evidences):
                            bot.editMessageText(message, '<b>❌ Índice de evidencia inválido</b>', parse_mode='html')
                            return
                        
                        evidence = evidences[evid_idx]
                        ev_name = evidence['evidence_name']
                        clean_name = ev_name
                        for user in evidence['group_users']:
                            marker = f"{USER_EVIDENCE_MARKER}{user}"
                            if marker in ev_name:
                                clean_name = ev_name.replace(marker, "").strip()
                                break
                        
                        short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                        bot.editMessageText(message, f'<b>🗑️ Eliminando evidencia:</b> <b>{clean_name[:50]}...</b>', parse_mode='html')
                        
                        success, ev_name, files_count = delete_evidence_from_cloud(
                            evidence['cloud_config'], 
                            evidence['evidence_data']
                        )
                        
                        if success:
                            admin_evidence_manager.refresh_data(force=True)
                            cloud_names = list(admin_evidence_manager.clouds_dict.keys())
                            
                            if cloud_idx < len(cloud_names):
                                current_evidences = admin_evidence_manager.clouds_dict.get(cloud_names[cloud_idx], [])
                                if current_evidences:
                                    result_msg = f"""
<b>✅ Eliminación exitosa</b>
🗑️ <b>Evidencia:</b> <b>{clean_name[:50]}</b>
📁 <b>Archivos eliminados:</b> <b>{files_count}</b>
☁️ <b>Nube:</b> <code>{short_name}</code>
                                    """
                                    bot.editMessageText(message, result_msg, parse_mode='html')
                                    time.sleep(1)
                                    show_updated_cloud(bot, message, cloud_idx)
                                else:
                                    result_msg = f"""
<b>✅ Eliminación completa</b>
🗑️ <b>Última evidencia eliminada</b>
📁 <b>Archivos borrados:</b> <b>{files_count}</b>
                                    """
                                    bot.editMessageText(message, result_msg, parse_mode='html')
                                    time.sleep(1)
                                    show_updated_all_clouds(bot, message)
                            else:
                                show_updated_all_clouds(bot, message)
                        else:
                            bot.editMessageText(message, f'<b>❌ Error al eliminar:</b> <b>{clean_name}</b>', parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_wipe_' in msgText:
                    try:
                        cloud_idx = extract_one_param_simple(msgText, '/adm_wipe_')
                        if cloud_idx is None:
                            bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /adm_wipe_0', parse_mode='html')
                            return
                        
                        if cloud_idx < 0 or cloud_idx >= len(admin_evidence_manager.clouds_dict):
                            bot.editMessageText(message, f'<b>❌ Índice inválido. Máximo:</b> <b>{len(admin_evidence_manager.clouds_dict)-1}</b>', parse_mode='html')
                            return
                        
                        cloud_name = list(admin_evidence_manager.clouds_dict.keys())[cloud_idx]
                        evidences = admin_evidence_manager.clouds_dict[cloud_name]
                        
                        if not evidences:
                            bot.editMessageText(message, f'<b>📭 La nube {cloud_idx} ya está vacía</b>', parse_mode='html')
                            return
                        
                        short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                        bot.editMessageText(message, f'<b>💣 Limpiando nube</b> <code>{short_name}</code>...', parse_mode='html')
                        
                        cloud_config = None
                        for cfg in AVAILABLE_CLOUDS:
                            if cfg.get('moodle_host') == cloud_name:
                                cloud_config = cfg
                                break
                        
                        if cloud_config:
                            success, deleted_count, total_files = delete_all_evidences_from_cloud(cloud_config)
                            if success:
                                admin_evidence_manager.refresh_data(force=True)
                                result_msg = f"""
<b>💥 Limpieza exitosa</b>
✅ <b>Nube:</b> <code>{short_name}</code>
✅ <b>Evidencias:</b> <b>{deleted_count}</b>
✅ <b>Archivos:</b> <b>{total_files}</b>
                                """
                                bot.editMessageText(message, result_msg, parse_mode='html')
                                time.sleep(1)
                                show_updated_all_clouds(bot, message)
                            else:
                                bot.editMessageText(message, f'<b>❌ Error al limpiar</b> <code>{short_name}</code>', parse_mode='html')
                        else:
                            bot.editMessageText(message, '<b>❌ No se encontró configuración</b>', parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_nuke' in msgText:
                    try:
                        total_evidences = len(admin_evidence_manager.current_list)
                        if total_evidences == 0:
                            bot.editMessageText(message, '<b>📭 No hay evidencias para eliminar</b>', parse_mode='html')
                            return
                        
                        bot.editMessageText(message, '<b>💣💣💣 Eliminación masiva...</b>', parse_mode='html')
                        results = []
                        deleted_total = 0
                        files_total = 0
                        
                        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                            cloud_config = None
                            for cfg in AVAILABLE_CLOUDS:
                                if cfg.get('moodle_host') == cloud_name:
                                    cloud_config = cfg
                                    break
                            
                            if cloud_config:
                                success, deleted_count, total_files = delete_all_evidences_from_cloud(cloud_config)
                                short_name = cloud_name.replace('https://', '').replace('http://', '').strip('/')
                                if success:
                                    deleted_total += deleted_count
                                    files_total += total_files
                                    results.append(f"✅ <code>{short_name}</code>: <b>{deleted_count} ev., {total_files} arch.</b>")
                                else:
                                    results.append(f"❌ <code>{short_name}</code>: <b>Error</b>")
                        
                        admin_evidence_manager.refresh_data(force=True)
                        final_msg = f"""
💥 <b>Eliminación masiva completada</b>
📊 <b>Evidencias:</b> <b>{deleted_total}</b>
📁 <b>Archivos:</b> <b>{files_total}</b>
"""
                        for result in results:
                            final_msg += f"\n{result}"
                        bot.editMessageText(message, final_msg, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_logs' in msgText:
                    try:
                        if not memory_stats.has_any_data():
                            bot.editMessageText(message, "<b>⚠️ No hay datos registrados.</b>", parse_mode='html')
                            return
                        
                        limit = 300
                        if '_' in msgText:
                            try:
                                limit = int(msgText.split('_')[2])
                            except: pass
                        
                        uploads = memory_stats.get_recent_uploads(limit)
                        deletes = memory_stats.get_recent_deletes(limit)
                        
                        logs_msg = "📋 <b>Últimos logs</b>\n\n"
                        if uploads:
                            logs_msg += "⬆️ <b>Subidas:</b>\n"
                            for log in uploads:
                                logs_msg += f"• <b>{log['timestamp']}</b> - <b>@{log['username']}</b>: <b>{log['filename']}</b> (<b>{log['file_size_formatted']}</b>)\n"
                            logs_msg += "\n"
                        if deletes:
                            logs_msg += "🗑️ <b>Eliminaciones:</b>\n"
                            for log in deletes:
                                if log['type'] == 'delete_all':
                                    logs_msg += f"• <b>{log['timestamp']}</b> - <b>@{log['username']}</b>: <b>Eliminación masiva ({log.get('deleted_evidences', 1)} ev.)</b>\n"
                                else:
                                    logs_msg += f"• <b>{log['timestamp']}</b> - <b>@{log['username']}</b>: <b>{log['filename']}</b>\n"
                        
                        if len(logs_msg) > 4000:
                            logs_msg = logs_msg[:4000] + "\n\n⚠️ <b>Truncado</b>"
                        bot.editMessageText(message, logs_msg, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener logs:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_users' in msgText:
                    try:
                        users = memory_stats.get_all_users()
                        if not users:
                            bot.editMessageText(message, "<b>⚠️ No hay usuarios registrados.</b>", parse_mode='html')
                            return
                        
                        users_msg = "👥 <b>Estadísticas por usuario</b>\n\n"
                        for user, data in sorted(users.items(), key=lambda x: x[1]['uploads'], reverse=True):
                            total_size_formatted = format_file_size(data['total_size'])
                            users_msg += f"👤 <b>Usuario:</b> <b>@{user}</b>\n   📤 <b>Subidas:</b> <b>{data['uploads']}</b>\n   🗑️ <b>Eliminaciones:</b> <b>{data['deletes']}</b>\n   💾 <b>Espacio:</b> <b>{total_size_formatted}</b>\n\n"
                        
                        if len(users_msg) > 4000:
                            users_msg = users_msg[:4000] + "\n\n⚠️ <b>Truncado</b>"
                        bot.editMessageText(message, users_msg, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener usuarios:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_uploads' in msgText:
                    try:
                        uploads = memory_stats.get_recent_uploads(15)
                        if not uploads:
                            bot.editMessageText(message, "<b>⚠️ No hay subidas registradas.</b>", parse_mode='html')
                            return
                        
                        uploads_msg = "📤 <b>Últimas subidas</b>\n\n"
                        for i, log in enumerate(uploads, 1):
                            uploads_msg += f"<b>{i}.</b> <b>{log['filename']}</b>\n   👤 <b>@{log['username']}</b> | 📏 <b>{log['file_size_formatted']}</b>\n\n"
                        bot.editMessageText(message, uploads_msg, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener subidas:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_deletes' in msgText:
                    try:
                        deletes = memory_stats.get_recent_deletes(15)
                        if not deletes:
                            bot.editMessageText(message, "<b>⚠️ No hay eliminaciones registradas.</b>", parse_mode='html')
                            return
                        
                        deletes_msg = "🗑️ <b>Últimas eliminaciones</b>\n\n"
                        for i, log in enumerate(deletes, 1):
                            if log['type'] == 'delete_all':
                                deletes_msg += f"<b>{i}.</b> <b>Eliminación masiva</b>\n   👤 <b>@{log['username']}</b> (<b>{log.get('deleted_evidences', 1)} ev.</b>)\n\n"
                            else:
                                deletes_msg += f"<b>{i}.</b> <b>{log['filename']}</b>\n   👤 <b>@{log['username']}</b>\n\n"
                        bot.editMessageText(message, deletes_msg, parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al obtener eliminaciones:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
                
                elif '/adm_cleardata' in msgText:
                    try:
                        if not memory_stats.has_any_data():
                            bot.editMessageText(message, "<b>⚠️ No hay datos para limpiar.</b>", parse_mode='html')
                            return
                        result = memory_stats.clear_all_data()
                        bot.editMessageText(message, f"<b>{result}</b>", parse_mode='html')
                    except Exception as e:
                        bot.editMessageText(message, f'<b>❌ Error al limpiar datos:</b> <b>{str(e)}</b>', parse_mode='html')
                    return
        
        # ============================================
        # COMANDOS REGULARES DE USUARIO
        # ============================================
        
        if '/mystats' in msgText:
            user_stats = memory_stats.get_user_stats(username)
            if user_stats:
                total_size_formatted = format_file_size(user_stats['total_size'])
                daily_size_formatted = format_file_size(user_stats.get('daily_size', 0))
                stats_msg = f"""
📊 <b>Tus estadísticas</b>
👤 <b>Usuario:</b> <b>@{username}</b>
📤 <b>Subidas:</b> <b>{user_stats['uploads']}</b>
🗑️ <b>Eliminaciones:</b> <b>{user_stats['deletes']}</b>
💾 <b>Espacio usado hoy:</b> <b>{daily_size_formatted} / {format_file_size(DAILY_LIMIT_BYTES)}</b>
💾 <b>Espacio histórico:</b> <b>{total_size_formatted}</b>
📅 <b>Última actividad:</b> <b>{user_stats['last_activity']}</b>
                """
            else:
                stats_msg = f"""
📊 <b>Tus estadísticas</b>
👤 <b>Usuario:</b> <b>@{username}</b>
📤 <b>Subidas:</b> <b>0</b>
🗑️ <b>Eliminaciones:</b> <b>0</b>
💾 <b>Espacio usado hoy:</b> <b>0 B / {format_file_size(DAILY_LIMIT_BYTES)}</b>

ℹ️ <b>Aún no tienes actividad registrada.</b>
                """
            bot.editMessageText(message, stats_msg, parse_mode='html')
            return

        elif msgText == '/cola' or msgText == '/colas':
            active_task, pending_list = queue_manager.get_user_snapshot(username)

            if not active_task and not pending_list:
                bot.editMessageText(message, "<b>📭 No tienes tareas en cola en este momento.</b>", parse_mode='html')
                return

            cola_msg = "🚦 <b>Tu cola de descargas</b>\n\n"

            if active_task:
                cola_msg += f"▶️ <b>En curso ahora:</b>\n   📄 <b>{active_task.filename}</b>\n   🗑️ /cancel_{active_task.task_id}\n\n"

            if pending_list:
                cola_msg += "⏳ <b>En espera:</b>\n"
                for idx, t in enumerate(pending_list, 1):
                    cola_msg += f"   <b>{idx}.</b> <b>{t.filename}</b>\n      🗑️ /cancel_{t.task_id}\n"
            else:
                cola_msg += "✅ <b>No tienes más enlaces esperando.</b>"

            bot.editMessageText(message, cola_msg, parse_mode='html')
            return
        
        elif '/files' == msgText:
            proxy = ProxyCloud.parse(user_info['proxy']) if user_info.get('proxy') else None
            try:
                requests.get(user_info['moodle_host'], timeout=5, proxies=proxy, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
            except:
                bot.editMessageText(message, f'<b>❌ La nube <code>{user_info["moodle_host"]}</code> no responde o está caída.</b>', parse_mode='html')
                return

            client = MoodleClient(user_info['moodle_user'],
                                   user_info['moodle_password'],
                                   user_info['moodle_host'],
                                   user_info['moodle_repo_id'],proxy=proxy)
            loged = client.login()
            if loged:
                all_evidences = client.getEvidences()
                visible_list = []
                search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                
                for ev in all_evidences:
                    if ev['name'].endswith(search_pattern):
                        clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                        file_count = len(ev['files']) if 'files' in ev else 0
                        visible_list.append({
                            'name': clean_name,
                            'file_count': file_count,
                            'original': ev
                        })
                
                if len(visible_list) > 0:
                    files_msg = "📁 <b>Tus evidencias</b>\n\n"
                    for idx, item in enumerate(visible_list):
                        files_msg += f"• <b>{item['name']}</b> [ <b>{item['file_count']}</b> ]\n  /txt_{idx} | /del_{idx}\n\n"
                    files_msg += f"<b>Total:</b> <b>{len(visible_list)} evidencia(s)</b>"
                    bot.editMessageText(message, files_msg, parse_mode='html')
                else:
                    bot.editMessageText(message, '<b>📭 No hay evidencias disponibles</b>', parse_mode='html')
                client.logout()
            else:
                bot.editMessageText(message,'<b>⚠️ Error: Revise su cuenta o el servidor deshabilitado:</b> <code>'+client.path+'</code>', parse_mode='html')
                
        elif '/txt_' in msgText:
            try:
                findex = int(str(msgText).split('_')[1])
                proxy = ProxyCloud.parse(user_info['proxy']) if user_info.get('proxy') else None
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    visible_list = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    if findex < 0 or findex >= len(visible_list):
                        bot.editMessageText(message, '<b>❌ Índice inválido. Use </b>/files<b> para ver la lista.</b>', parse_mode='html')
                        client.logout()
                        return
                    
                    evindex = visible_list[findex]['original']
                    clean_name = visible_list[findex]['clean_name']
                    txtname = clean_name + '.txt'
                    sendTxt(txtname, evindex['files'], update, bot, user_info=user_info)
                    client.logout()
                    bot.editMessageText(message,'<b>📄 TXT enviado con éxito.</b>', parse_mode='html')
                else:
                    bot.editMessageText(message,'<b>⚠️ Error de conexión o cuenta inválida.</b>', parse_mode='html')
            except ValueError:
                bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /txt_0', parse_mode='html')
            except Exception as e:
                bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
             
        elif '/del_' in msgText:
            try:
                findex = int(str(msgText).split('_')[1])
                proxy = ProxyCloud.parse(user_info['proxy']) if user_info.get('proxy') else None
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    visible_list = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    if findex < 0 or findex >= len(visible_list):
                        bot.editMessageText(message, '<b>❌ Índice inválido. Use </b>/files<b> para ver la lista.</b>', parse_mode='html')
                        client.logout()
                        return
                    
                    evfile = visible_list[findex]['original']
                    evidence_clean_name = visible_list[findex]['clean_name']
                    file_count = len(evfile['files']) if 'files' in evfile else 0
                    
                    client.deleteEvidence(evfile)
                    all_evidences = client.getEvidences()
                    
                    updated_visible_list = []
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            updated_visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    client.logout()
                    memory_stats.log_delete(
                        username=username,
                        filename=f"{evidence_clean_name} ({file_count} archivos)",
                        evidence_name=evidence_clean_name,
                        moodle_host=user_info['moodle_host']
                    )

                    if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                        try:
                            clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                            msg_log = (f"<b>🗑️ ¡Evidencia eliminada!</b>\n\n"
                                       f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                       f"<b>📄 Evidencia:</b> <b>{evidence_clean_name}</b>\n"
                                       f"<b>📁 Archivos:</b> <b>{file_count}</b>\n"
                                       f"<b>☁️ Nube:</b> <code>{clean_host}</code>")
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar eliminación al grupo: {e}")
                    
                    confirmation_msg = f"🗑️ <b>Evidencia eliminada:</b> <b>{evidence_clean_name}</b>\n📁 <b>Archivos borrados:</b> <b>{file_count}</b>\n"
                    if len(updated_visible_list) > 0:
                        confirmation_msg += "📋 <b>Tus evidencias actualizadas:</b>\n\n"
                        for idx, item in enumerate(updated_visible_list):
                            clean_name = item['clean_name']
                            item_file_count = len(item['original']['files']) if 'files' in item['original'] else 0
                            confirmation_msg += f"• <b>{clean_name}</b> [ <b>{item_file_count}</b> ]\n  /txt_{idx} | /del_{idx}\n\n"
                        bot.editMessageText(message, confirmation_msg, parse_mode='html')
                    else:
                        confirmation_msg += "<b>📭 No hay evidencias disponibles</b>"
                        bot.editMessageText(message, confirmation_msg, parse_mode='html')
                else:
                    bot.editMessageText(message,'<b>⚠️ Error al conectar con la nube.</b>', parse_mode='html')
            except ValueError:
                bot.editMessageText(message, '<b>❌ Formato incorrecto. Use:</b> /del_0', parse_mode='html')
            except Exception as e:
                bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(e)}</b>', parse_mode='html')
                
        elif '/delall' in msgText:
            try:
                proxy = ProxyCloud.parse(user_info['proxy']) if user_info.get('proxy') else None
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],
                                       proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    user_evidences = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            user_evidences.append(ev)
                    
                    if not user_evidences:
                        bot.editMessageText(message, '<b>📭 No hay evidencias disponibles</b>', parse_mode='html')
                        client.logout()
                        return
                    
                    total_evidences = len(user_evidences)
                    total_files = sum(len(ev.get('files', [])) for ev in user_evidences)
                    
                    for item in user_evidences:
                        try:
                            client.deleteEvidence(item)
                        except: pass
                    
                    client.logout()
                    memory_stats.log_delete_all(
                        username=username, 
                        deleted_evidences=total_evidences, 
                        deleted_files=total_files,
                        moodle_host=user_info['moodle_host']
                    )

                    if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                        try:
                            clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                            msg_log = (f"<b>🗑️💥 ¡Eliminación masiva!</b>\n\n"
                                       f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                                       f"<b>📊 Evidencias borradas:</b> <b>{total_evidences}</b>\n"
                                       f"<b>📁 Archivos borrados:</b> <b>{total_files}</b>\n"
                                       f"<b>☁️ Nube:</b> <code>{clean_host}</code>")
                            bot.sendMessage(LOG_GROUP_ID, msg_log, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar eliminación masiva al grupo: {e}")
                    
                    deletion_msg = f"🗑️ <b>Eliminación masiva completada</b>\n\n• <b>Evidencias eliminadas:</b> <b>{total_evidences}</b>\n• <b>Archivos borrados:</b> <b>{total_files}</b>\n\n<b>✅ ¡Todas tus evidencias han sido eliminadas!</b>"
                    bot.editMessageText(message, deletion_msg, parse_mode='html')
                else:
                    bot.editMessageText(message,'<b>⚠️ Error al conectar con la cuenta.</b>', parse_mode='html')
            except Exception as ex:
                bot.editMessageText(message, f'<b>❌ Error:</b> <b>{str(ex)}</b>', parse_mode='html')
                
        elif 'http' in msgText:
            url = msgText
            file_size = 0
            filename = url.split('/')[-1] or "Desconocido"
            
            try:
                headers = {}
                if user_info['proxy']:
                    proxy_dict = ProxyCloud.parse(user_info['proxy'])
                    if 'http' in proxy_dict:
                        headers.update({'Proxy': proxy_dict['http']})
                
                response = requests.head(url, allow_redirects=True, timeout=5, headers=headers)
                file_size = int(response.headers.get('content-length', 0))
                
                cd = response.headers.get('content-disposition')
                if cd and 'filename=' in cd:
                    filename = cd.split('filename=')[1].strip('"\'')
                else:
                    filename = unquote(filename)
            except: pass

            if username.lower() != ADMIN_USERNAME.lower():
                memory_stats.check_and_update_daily_reset(username)
                user_st = memory_stats.get_user_stats(username)
                current_daily_size = user_st['daily_size'] if user_st else 0
                
                if DAILY_LIMIT_BYTES > 0 and current_daily_size + file_size > DAILY_LIMIT_BYTES:
                    send_reaction(chat_id, update.message.message_id, "💩")
                    if current_daily_size == 0:
                        limit_msg = (
                            f"<b>🚫 Límite diario excedido</b>\n\n"
                            f"<b>Estimado usuario @{username}, el archivo que intenta procesar pesa {format_file_size(file_size)}, "
                            f"lo cual excede el límite diario permitido de {format_file_size(DAILY_LIMIT_BYTES)}. "
                            f"No es posible procesar este archivo.</b>"
                        )
                        group_limit_msg = (
                            f"<b>🚫 ¡Límite diario excedido!</b>\n\n"
                            f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                            f"<b>⚖️ Archivo:</b> <b>{format_file_size(file_size)}</b>\n"
                            f"<b>⚠️ Detalle:</b> <b>Supera el límite de {format_file_size(DAILY_LIMIT_BYTES)} diario</b>"
                        )
                    else:
                        limit_msg = (
                            f"<b>🚫 Límite diario alcanzado</b>\n\n"
                            f"<b>Estimado usuario @{username}, ya ha consumido {format_file_size(current_daily_size)} de su cuota diaria de {format_file_size(DAILY_LIMIT_BYTES)}. "
                            f"Intentar procesar este archivo de {format_file_size(file_size)} excedería su límite permitido. "
                            f"Su cuota se restablecerá automáticamente al cambiar el día.</b>"
                        )
                        group_limit_msg = (
                            f"<b>🚫 ¡Cuota diaria superada!</b>\n\n"
                            f"<b>👤 Usuario:</b> <b>@{username}</b>\n"
                            f"<b>📊 Consumo previo:</b> <b>{format_file_size(current_daily_size)}</b>\n"
                            f"<b>⚖️ Archivo intentado:</b> <b>{format_file_size(file_size)}</b>\n"
                            f"<b>⚠️ Detalle:</b> <b>La suma excede el límite de {format_file_size(DAILY_LIMIT_BYTES)} diario</b>"
                        )

                    bot.editMessageText(message, limit_msg, parse_mode='html')
                    send_sticker(chat_id, "CAACAgEAAxkBAAIoWmqA9ruIyyqZw_C2PTIr47iOS-6MAAK9BgACnFgJRF49GlLpEVF9PQQ")
                    
                    if LOG_GROUP_ID != 0:
                        try:
                            bot.sendMessage(LOG_GROUP_ID, group_limit_msg, parse_mode='html')
                        except Exception as e:
                            print(f"Error al notificar bloqueo por límite diario al grupo: {e}")
                    return
            
            send_reaction(chat_id, update.message.message_id, "⚡")

            task_id = str(thread.id) if (thread and hasattr(thread, 'id') and thread.id) else createID()
            task, is_immediate, position = queue_manager.submit(username, url, chat_id, task_id, filename=filename)

            if is_immediate:
                if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                    try:
                        clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                        tamano_formateado = format_file_size(file_size) if file_size > 0 else "Desconocido"
                        mensaje_log = (f"<b>🔔 ¡Nuevo enlace recibido!</b>\n\n👤 <b>Usuario:</b> <b>@{username}</b>\n📄 <b>Nombre:</b> <b>{filename}</b>\n⚖️ <b>Peso:</b> <b>{tamano_formateado}</b>\n🔗 <b>Enlace:</b> <code>{url}</code>\n☁️ <b>Nube:</b> <code>{clean_host}</code>")
                        bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                    except Exception as e:
                        print(f"Error al notificar enlace: {e}")

                if thread and not hasattr(thread, 'id'):
                    thread.id = task_id
                task.thread_ctx = thread
                ddl(update,bot,message,url,file_name='',thread=thread)
            else:
                if LOG_GROUP_ID != 0 and username.lower() != ADMIN_USERNAME.lower():
                    try:
                        clean_host = user_info['moodle_host'].replace('https://', '').replace('http://', '').strip('/')
                        tamano_formateado = format_file_size(file_size) if file_size > 0 else "Desconocido"
                        mensaje_log = (f"<b>⏳ ¡Enlace en cola de espera!</b>\n\n👤 <b>Usuario:</b> <b>@{username}</b>\n📄 <b>Nombre:</b> <b>{filename}</b>\n⚖️ <b>Peso:</b> <b>{tamano_formateado}</b>\n📊 <b>Posición:</b> <b>#{position}</b>\n☁️ <b>Nube:</b> <code>{clean_host}</code>")
                        bot.sendMessage(LOG_GROUP_ID, mensaje_log, parse_mode='html')
                    except Exception as e:
                        print(f"Error al notificar enlace en cola: {e}")

                queue_pos_msg = f"""
<b>⏳ Enlace en cola de espera</b>

📄 <b>Archivo:</b> <b>{filename}</b>
📊 <b>Posición en tu cola:</b> <b>#{position}</b>
⚙️ <b>Se procesará automáticamente al terminar tu tarea actual.</b>

🗑️ <b>Cancelar este turno:</b> /cancel_{task_id}
📋 <b>Ver tu cola completa:</b> <b>/cola</b>
                """
                bot.editMessageText(message, queue_pos_msg, parse_mode='html')
        else:
            invalid_msg = (
                "<b>⚠️ Comando o formato no reconocido.</b>\n\n"
                "💡 <i>Envía un enlace de descarga válido o escribe /start para ver la lista de comandos disponibles.</i>"
            )
            bot.editMessageText(message, invalid_msg, parse_mode='html')
            
    except Exception as ex:
        print(f"Error general onmessage: {str(ex)}")
        print(traceback.format_exc())

def main():
    bot = PyrogramBotClient(BOT_TOKEN)
    bot.onMessage(onmessage)
    bot.run()

if __name__ == '__main__':
    try:
        main()
    except:
        main()
