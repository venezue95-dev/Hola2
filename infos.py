import datetime
import urllib.parse
import html
import time
import os

def sizeof_fmt(num, suffix='B'):
    """Formatea los bytes a un estilo limpio (KB, MB, GB) sin la 'i' y sin decimales .0 innecesarios"""
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            if unit == '':
                return f"{int(num)} {unit}{suffix}"
            formatted = f"{num:.1f}"
            if formatted.endswith('.0'):
                formatted = formatted[:-2]
            return f"{formatted} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"

def text_progres(index, max):
    try:
        if max < 1:
            max += 1
        porcent_val = index / max
        porcent_val *= 100
        porcent_val = round(porcent_val)
        make_text = ''
        index_make = 1
        make_text += '\n[ '
        while index_make < 21:
            if porcent_val >= index_make * 5:
                make_text += '⬢'
            else:
                make_text += '⬡'
            index_make += 1
        make_text += ' ]\n'
        return make_text
    except Exception:
        return ''

def porcent(index, max):
    if max < 1:
        max = 1
    porcent_val = index / max
    porcent_val *= 100
    porcent_val = round(porcent_val)
    return porcent_val

def createDownloading(filename, totalBits, currentBits, speed, time_val, tid=''):
    msg = '<b>⬇️ Descargando archivo...</b>\n\n'
    msg += f'<b>📄 Nombre: {filename}</b>\n'
    if totalBits and totalBits > 0:
        msg += f'<b>{text_progres(currentBits, totalBits)}</b>\n'
        msg += f'<b>📊 Porcentaje: {porcent(currentBits, totalBits)}%</b>\n\n'
        msg += f'<b>💾 Tamaño total: {sizeof_fmt(totalBits)}</b>\n\n'
    else:
        msg += '<b>📊 Porcentaje: calculando...</b>\n\n'
        msg += '<b>💾 Tamaño total: no indicado por el servidor</b>\n\n'
    msg += f'<b>📥 Descargado: {sizeof_fmt(currentBits)}</b>\n\n'
    msg += f'<b>⚡ Velocidad: {sizeof_fmt(speed)}/s</b>\n\n'
    msg += f'<b>⏱️ Tiempo: {datetime.timedelta(seconds=int(time_val))}</b>\n\n'

    if tid != '':
        msg += f'/cancel_{tid}'
    return msg

def createUploading(filename, totalBits, currentBits, speed, time_val, originalname='', tid=''):
    msg = '<b>⬆️ Subiendo a la nube...</b>\n\n'
    if originalname != '':
        msg += f'<b>📁 Nombre: {originalname}</b>\n'
        msg += '<b>📤 Procesando el archivo...</b>\n'
    else:
        msg += f'<b>📁 Nombre: {filename}</b>\n'
    msg += f'<b>{text_progres(currentBits, totalBits)}</b>\n'
    msg += f'<b>📊 Porcentaje: {porcent(currentBits, totalBits)}%</b>\n\n'
    msg += f'<b>💾 Tamaño total: {sizeof_fmt(totalBits)}</b>\n\n'
    msg += f'<b>📤 Subido: {sizeof_fmt(currentBits)}</b>\n\n'
    msg += f'<b>⚡ Velocidad: {sizeof_fmt(speed)}/s</b>\n\n'
    msg += f'<b>⏱️ Tiempo: {datetime.timedelta(seconds=int(time_val))}</b>\n\n'

    if tid != '':
        msg += f'/cancel_{tid}'
    return msg

def createCompresing(filename, filesize, splitsize):
    msg = '<b>⚙️ Preparando el archivo...</b>\n\n'
    msg += f'<b>📁 Nombre: {filename}</b>\n\n'
    msg += f'<b>📊 Tamaño total: {sizeof_fmt(filesize)}</b>\n\n'
    msg += '<i>La transferencia se está preparando de forma segura.</i>\n'
    return msg

def createFinishUploading(filename, filesize, split_size, current, count, findex):
    msg = '<b>✅ ¡Proceso completado con éxito!</b>\n\n'
    msg += f'<b>📁 Nombre: {filename}</b>\n\n'
    msg += f'<b>📊 Tamaño total: {sizeof_fmt(filesize)}</b>\n\n'
    msg += '<i>Tu archivo está listo para descargar.</i>'
    return msg

def createFileMsg(filename, files):
    if len(files) > 0:
        msg = '<b>🔗 Enlaces de descarga:</b>\n'
        for f in files:
            url = urllib.parse.unquote(f.get('directurl') or f.get('url') or '', encoding='utf-8', errors='replace')
            name = html.escape(str(f.get('name') or filename), quote=False)
            # El código https://5.4.3.2.1:... es un identificador copiable,
            # no una URL HTTP real: Telegram lo interpreta erróneamente como
            # host:puerto si se coloca dentro de <a href="...">.
            if url.startswith('https://5.4.3.2.1:'):
                safe_code = html.escape(url, quote=False)
                msg += (
                    f"<b>➥ {name}</b>\n"
                    f"<i>Mantén pulsado para copiar el código completo:</i>\n"
                    f"<code>{safe_code}</code>\n"
                )
            else:
                safe_url = html.escape(url, quote=True)
                msg += f"<a href=\"{safe_url}\"><b>➥ {name}</b></a>\n"
        return msg
    return ''

def createFilesMsg(evfiles):
    msg = f'<b>📁 Archivos guardados ({len(evfiles)})</b>\n\n'
    i = 0
    for f in evfiles:
        try:
            fextarray = str(f['files'][0]['name']).split('.')
            fext = ''
            if len(fextarray) >= 3:
                fext = '.' + fextarray[-2]
            else:
                fext = '.' + fextarray[-1]
            fname = f['name'] + fext
            msg += f'<b>📄 {fname}</b>\n'
            msg += f'<b>👁️ /txt_{i}  |  🗑️ /del_{i}</b>\n\n'
            i += 1
        except Exception:
            pass
    return msg

def createStat(username, userdata, isadmin):
    msg = '<b>⚙️ Configuración de usuario</b>\n\n'
    msg += f'<b>👤 Nombre: @{username}</b>\n'
    msg += f'<b>👤 Usuario Moodle: {userdata["moodle_user"]}</b>\n'
    msg += f'<b>🔑 Contraseña: {userdata["moodle_password"]}</b>\n'
    msg += f'<b>🌐 Host: {userdata["moodle_host"]}</b>\n'
    if userdata['cloudtype'] == 'moodle':
        msg += f'<b>📁 RepoID: {userdata["moodle_repo_id"]}</b>\n'
    msg += f'<b>☁️ Tipo de nube: {userdata["cloudtype"]}</b>\n'
    msg += f'<b>⬆️ Tipo de subida: {userdata["uploadtype"]}</b>\n'
    if userdata['cloudtype'] == 'cloud':
        msg += f'<b>📂 Directorio: /{userdata["dir"]}</b>\n'
    msg += f'<b>📏 Límite de zips: {sizeof_fmt(userdata["zips"] * 1024 * 1024)}</b>\n\n'
    
    msg_admin = 'No'
    if isadmin:
        msg_admin = 'Sí'
    msg += f'<b>👑 Administrador: {msg_admin}</b>\n'
    
    proxy = 'No'
    if userdata['proxy'] != '':
        proxy = 'Sí'
    tokenize = 'No'
    if userdata['tokenize'] != 0:
        tokenize = 'Sí'
    msg += f'<b>🔗 Proxy: {proxy}</b>\n'
    msg += f'<b>🔐 Tokenización: {tokenize}</b>\n\n'
    return msg
    
