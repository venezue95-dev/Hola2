![Esta es una imagen](https://github.com/SokyFre2/enlace-Directo/blob/main/assets/Images/IMG_20220710_180342_403.jpg)
# @UploadFreBot
Bot De Telegram : @UploadFreBot , Descargador gratis de contenido desde internet a hacia moodles , nexcloud en cuba

# Comandos En El Bot (Usuarios Nomales)
/start : Inicar Bot , Te Da La INfo
/tutorial : Te Da un tutorial basico de uso del bot q puedes echarle un ojo
/myuser : Obtiene la informacion del usuario q esta usando el bot
/zips : Configura el tamano de las partes comprimidas 7z
/account: COnfigura su cuenta de nube en el bot
/host : Configura el Host Al Cual ba a subir los archivos el bot x ejemplo https://moodle.uclv.edu.cu/ (Moodle o Nexcloud)
/repoid : EN EL caso de las moodles cada nube tiene su repoid q hay q saber extraerlo y configurarsel al bot para poder subir
/cloud : Alterna El tipo de subida a nubes ya sea cloud o moodle , en caso de cloud es nexcloud pero para simplificar se pone cloud
/tokenize_on : Enciende el modo tokenize , se recomienda no usar a no se q disponga de una de las apps oficiales de descarga del bot 
/tokenize_off : Apaga el modo tokenize
/uptype : Configure el modo de subir de moodle ya sea draft , evidence , blog y calendario
/proxy : Configura UN Proxy Para Las Subidas Del Bot , contactar en telegram a @SokyShop para contratar uno
/files : En caso de tener activa el uptype (evidence) este comando le da una lista de archivo q se encuentra en las evidencias de la nube
/delall : En caso de tener activa el uptype (evidence) este comando borra todos los archivos en la lista de evidencia de la nube
/dir : En caso de tener activo cloud configure el directorio base en la nexcloud donde se va a subir los archivos


# Comandos En El Bot (Administrador) 
/adduser : permite un usuario de telegram tener acceso al bot
/banuser : quita acceso al bot de un usuario de telegram
/getdb : Obten la base de datos donde se almacenan la info de los usarios en el bot

# Deploy Directo (Heroku)
[![Heroku Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/SokyFre2/uploadFre)

## Configuración segura y subida por partes

Las credenciales no deben estar en `main.py`. Copia `.env.example` a `.env` y
rellena las variables de entorno antes de arrancar el bot. El token de
Telegram y las contraseñas que estuvieron en versiones anteriores deben
revocarse o cambiarse.

El transporte de Telegram usa **Pyrogram** real. Además de `BOT_TOKEN`, son
obligatorios `TELEGRAM_API_ID` y `TELEGRAM_API_HASH`, obtenidos en
`my.telegram.org`. El bot acepta enlaces escritos y también documentos,
vídeos, audios y animaciones enviados directamente al chat.

El tamaño máximo de cada parte se toma directamente del límite `zips`
configurado para la nube seleccionada. Si el archivo es menor que ese límite,
se sube en una sola parte; si es mayor, se divide en partes del tamaño de esa
nube. El flujo usa chunks binarios crudos y sube cada parte por separado a
Moodle. `CHUNK_SIZE_MB` se conserva solo por compatibilidad con configuraciones
anteriores y ya no limita el flujo principal.

También se incluye `ChunkedMoodleUploader.py` como capa reutilizable y
`chunk_code.py` para generar y reconstruir el código único de descarga.

### Descargar un código de chunks

El resultado no es una URL HTTP nativa de Moodle: es un código con prefijo `https://5.4.3.2.1:` que
contiene el manifiesto de las partes. Para reconstruir el archivo en otro
equipo:

```bash
pip install -r requirements.txt
python chunk_downloader.py 'https://5.4.3.2.1:...'
```

También se puede indicar otro nombre de salida:

```bash
python chunk_downloader.py 'https://5.4.3.2.1:...' -o archivo_reconstruido.bin
```

El descargador ordena las partes, las descarga en streaming y verifica el
tamaño final antes de terminar. Los códigos antiguos `REVISTA1:` y `ETCHUNK1:`
siguen siendo aceptados.

### Cobertura de URLs y límites

El bot usa una ruta común con timeouts, reintentos limitados, nombres locales
seguros, límite de tamaño (`MAX_DOWNLOAD_BYTES`, 2 GiB por defecto), bloqueo de
hosts privados/reservados y validación de cada redirección. También reconoce
MediaFire y Google Drive públicos, además de los enlaces que `yt-dlp` pueda
resolver dentro de `YTDLP_ALLOWED_HOSTS`. La lista inicial incluye YouTube,
Vimeo, Dailymotion, TikTok, Instagram, X, Facebook, Twitch, SoundCloud,
Bandcamp y Reddit; ampliar esa lista no garantiza que el sitio funcione.

No se habilitan cookies, contraseñas, CAPTCHA, DRM, paywalls, torrents ni
proxies de evasión. Las herramientas como gallery-dl, Streamlink, aria2,
Megatools, rclone y JDownloader deben instalarse y auditarse como adaptadores
separados; no se ejecutan automáticamente desde una URL del usuario.
