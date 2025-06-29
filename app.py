from flask import Flask, request, render_template, send_from_directory, redirect, url_for
import yt_dlp
import os
import subprocess
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Directorios base
BASE_DIR = os.path.join('static', 'downloads')
INDIVIDUAL_FOLDER = os.path.join(BASE_DIR, 'individuales')
ACAPELLAS_FOLDER = os.path.join(BASE_DIR, 'acapellas')  # Se creará solo cuando se use
PLAYLIST_FOLDER = os.path.join(BASE_DIR, 'playlists')   # Se creará solo cuando se use

app.config['UPLOAD_FOLDER'] = INDIVIDUAL_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'mp3'}

# Crear solo la carpeta de individuales al inicio
os.makedirs(INDIVIDUAL_FOLDER, exist_ok=True)

# Verificar FFmpeg
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

if not check_ffmpeg():
    print("FFmpeg no está instalado o no está en el PATH.")
    exit(1)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    archivos = [f for f in os.listdir(INDIVIDUAL_FOLDER) if f.endswith('.mp3')]
    return render_template('index.html', archivos=archivos)

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
            'quiet': True,
        }) as ydl:
            ydl.extract_info(url, download=True)

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error al descargar: {str(e)}", 500

@app.route('/playlist_download', methods=['POST'])
def playlist_download():
    url = request.form['playlist_url']
    if not url:
        return "URL de playlist inválida", 400

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            playlist_title = info.get('title', 'playlist_sin_nombre').replace('/', '_')
            playlist_path = os.path.join(PLAYLIST_FOLDER, playlist_title)
            os.makedirs(playlist_path, exist_ok=True)  # Se crea solo si hace falta

        with yt_dlp.YoutubeDL({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(playlist_path, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }) as ydl:
            ydl.download([url])

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error al descargar playlist: {str(e)}", 500

@app.route('/subir_y_separar', methods=['POST'])
def subir_y_separar():
    if 'archivo' not in request.files:
        return "No se envió archivo", 400

    archivo = request.files['archivo']
    if archivo.filename == '':
        return "Archivo vacío", 400

    if archivo and allowed_file(archivo.filename):
        filename = secure_filename(archivo.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        archivo.save(filepath)

        # Asegurar que ACAPELLAS_FOLDER exista solo si se necesita
        os.makedirs(ACAPELLAS_FOLDER, exist_ok=True)

        try:
            # Ejecutar Demucs con --two-stems vocals
            comando = [
                'demucs',
                '--two-stems', 'vocals',
                '--out', ACAPELLAS_FOLDER,
                filepath
            ]
            subprocess.run(comando, check=True)

            # Ruta esperada de salida
            nombre_base = os.path.splitext(filename)[0]
            output_dir = os.path.join(ACAPELLAS_FOLDER, 'htdemucs', nombre_base)

            vocals_path = os.path.join(output_dir, 'vocals.wav')
            instrumental_path = os.path.join(output_dir, 'no_vocals.wav')

            if not os.path.exists(vocals_path):
                return "No se generó el archivo vocals.wav", 500
            return redirect(url_for('index'))


        except Exception as e:
            return f"Error al procesar con Demucs: {e}", 500

    return "Archivo inválido. Solo se permiten archivos .mp3", 400

@app.route('/download/<path:filepath>')
def download_file(filepath):
    dirpath = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    return send_from_directory(dirpath, filename, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
