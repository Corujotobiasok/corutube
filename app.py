from flask import Flask, request, render_template, send_from_directory, redirect, url_for, jsonify, session
import yt_dlp
import os
import subprocess
import shutil
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configuración de versiones
PREMIUM_CODE = "123-456-789"
MAX_PLAYLISTS_FREE = 1
MAX_SONGS_FREE = 10
MAX_SEPARATIONS_FREE = 3

# ======= RUTA INTERNA A FFMPEG =========
FFMPEG_PATH = os.path.abspath(os.path.join('tools', 'ffmpeg.exe'))
os.environ['PATH'] = os.path.dirname(FFMPEG_PATH) + os.pathsep + os.environ['PATH']
# =======================================

# Ruta base en Documents/CoruTube
DOCUMENTS_PATH = os.path.join(os.path.expanduser('~'), 'Documents')
CORUTUBE_DIR = os.path.join(DOCUMENTS_PATH, 'CoruTube')
INDIVIDUAL_FOLDER = os.path.join(CORUTUBE_DIR, 'individuales')
PROCESADAS_FOLDER = os.path.join(CORUTUBE_DIR, 'procesadas')
PLAYLIST_FOLDER = os.path.join(CORUTUBE_DIR, 'playlists')
CONFIG_FILE = os.path.join(CORUTUBE_DIR, 'config.json')

# Crear carpetas principales
os.makedirs(INDIVIDUAL_FOLDER, exist_ok=True)
os.makedirs(PROCESADAS_FOLDER, exist_ok=True)
os.makedirs(PLAYLIST_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = INDIVIDUAL_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'mp3'}

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'premium': False, 'last_playlist_date': None, 'playlist_count': 0, 
            'last_separation_date': None, 'separation_count': 0}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def reset_daily_counts_if_needed(config):
    today = datetime.now().date()
    
    if config.get('last_playlist_date'):
        last_date = datetime.strptime(config['last_playlist_date'], '%Y-%m-%d').date()
        if last_date != today:
            config['playlist_count'] = 0
            config['last_playlist_date'] = today.strftime('%Y-%m-%d')
    
    if config.get('last_separation_date'):
        last_date = datetime.strptime(config['last_separation_date'], '%Y-%m-%d').date()
        if last_date != today:
            config['separation_count'] = 0
            config['last_separation_date'] = today.strftime('%Y-%m-%d')
    
    return config

@app.route('/')
def index():
    config = load_config()
    config = reset_daily_counts_if_needed(config)
    save_config(config)
    
    archivos = [f for f in os.listdir(INDIVIDUAL_FOLDER) if f.endswith('.mp3')]
    return render_template('index.html', archivos=archivos, premium=config['premium'])

@app.route('/activate_premium', methods=['POST'])
def activate_premium():
    code = request.form.get('code', '').strip()
    if code == PREMIUM_CODE:
        config = load_config()
        config['premium'] = True
        save_config(config)
        return jsonify({'success': True, 'message': '¡Versión Premium activada correctamente!'})
    else:
        return jsonify({'success': False, 'message': 'Código inválido. Intente nuevamente.'})

@app.route('/single_download', methods=['POST'])
def single_download():
    url = request.form['youtube_url']
    if not url:
        return "URL inválida", 400

    try:
        with yt_dlp.YoutubeDL({
            'format': 'bestaudio/best',
            'noplaylist': True,
            'outtmpl': os.path.join(INDIVIDUAL_FOLDER, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ffmpeg_location': FFMPEG_PATH,
            'quiet': True,
        }) as ydl:
            ydl.extract_info(url, download=True)

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error al descargar: {str(e)}", 500

@app.route('/playlist_download', methods=['POST'])
def playlist_download():
    config = load_config()
    config = reset_daily_counts_if_needed(config)
    
    if not config['premium']:
        if config['playlist_count'] >= MAX_PLAYLISTS_FREE:
            return f"Límite diario alcanzado (máximo {MAX_PLAYLISTS_FREE} playlist por día en versión gratuita)", 403
        
        config['playlist_count'] += 1
        config['last_playlist_date'] = datetime.now().date().strftime('%Y-%m-%d')
        save_config(config)

    url = request.form['playlist_url']
    if not url:
        return "URL de playlist inválida", 400

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            playlist_title = info.get('title', 'playlist_sin_nombre').replace('/', '_')
            playlist_path = os.path.join(PLAYLIST_FOLDER, playlist_title)
            os.makedirs(playlist_path, exist_ok=True)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(playlist_path, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ffmpeg_location': FFMPEG_PATH,
            'quiet': True,
        }

        if not config['premium']:
            ydl_opts['playlistend'] = MAX_SONGS_FREE - 1

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error al descargar playlist: {str(e)}", 500

@app.route('/subir_y_separar', methods=['POST'])
def subir_y_separar():
    config = load_config()
    config = reset_daily_counts_if_needed(config)
    
    if not config['premium']:
        if config['separation_count'] >= MAX_SEPARATIONS_FREE:
            return f"Límite diario alcanzado (máximo {MAX_SEPARATIONS_FREE} separaciones por día en versión gratuita)", 403
        
        config['separation_count'] += 1
        config['last_separation_date'] = datetime.now().date().strftime('%Y-%m-%d')
        save_config(config)

    if 'archivo' not in request.files:
        return "No se envió archivo", 400

    archivo = request.files['archivo']
    if archivo.filename == '':
        return "Archivo vacío", 400

    stems_seleccionados = request.form.getlist('stems')
    if not stems_seleccionados:
        return "Debes seleccionar al menos una opción de extracción", 400

    # En versión gratuita solo permitir vocals
    if not config['premium'] and ('other' in stems_seleccionados or 'drums' in stems_seleccionados or 'bass' in stems_seleccionados):
        return "Esta función solo está disponible en la versión Premium", 403

    filename = secure_filename(archivo.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    archivo.save(filepath)

    try:
        if stems_seleccionados == ['vocals']:
            comando = ['demucs', '--two-stems', 'vocals', '--out', PROCESADAS_FOLDER, filepath]
        else:
            comando = ['demucs', '--out', PROCESADAS_FOLDER, filepath]

        subprocess.run(comando, check=True)

        nombre_base = os.path.splitext(filename)[0]
        output_dir = os.path.join(PROCESADAS_FOLDER, 'htdemucs', nombre_base)
        destino_final = os.path.join(PROCESADAS_FOLDER, nombre_base)
        os.makedirs(destino_final, exist_ok=True)

        # Mover archivos seleccionados
        todos = {
            'vocals': 'vocals.wav',
            'drums': 'drums.wav',
            'bass': 'bass.wav',
            'other': 'melodia.wav' if 'other' in stems_seleccionados else 'other.wav'
        }

        for stem, archivo_nombre in todos.items():
            origen = os.path.join(output_dir, archivo_nombre if stem != 'other' else 'other.wav')
            destino = os.path.join(destino_final, archivo_nombre)
            if stem in stems_seleccionados and os.path.exists(origen):
                if stem == 'other':
                    os.rename(origen, destino)  # Rename to melodia.wav
                else:
                    shutil.move(origen, destino)

        shutil.rmtree(os.path.join(PROCESADAS_FOLDER, 'htdemucs'), ignore_errors=True)

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error al procesar con Demucs: {e}", 500

@app.route('/download/<path:filepath>')
def download_file(filepath):
    dirpath = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    return send_from_directory(dirpath, filename, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)