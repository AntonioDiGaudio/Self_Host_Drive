# Importazione delle librerie necessarie
from flask import Flask, request, send_from_directory, render_template, redirect, url_for, session
from flask_basicauth import BasicAuth
from werkzeug.utils import secure_filename
import os
import requests
import platform
import uuid
import shelve
import logging
import shutil
import zipfile

# Creazione dell'istanza dell'applicazione Flask
app = Flask(__name__)

# Impostazione della chiave segreta per le sessioni Flask
app.secret_key = 'your_secret_key'  # La chiave segreta è utilizzata per firmare i cookie di sessione

# Configurazione dell'autenticazione di base
app.config['BASIC_AUTH_USERNAME'] = 'admin'  # Nome utente per l'autenticazione
app.config['BASIC_AUTH_PASSWORD'] = 'password'  # Password per l'autenticazione
basic_auth = BasicAuth(app)  # Inizializzazione dell'autenticazione di base

# Configurazione della cartella di upload e delle estensioni di file consentite
UPLOAD_FOLDER = 'uploads'  # Cartella dove verranno caricati i file
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp3', 'mp4', 'doc', 'docx', 'zip'}

# Creazione della cartella di upload se non esiste già
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Token e ID della chat per il bot di Telegram
TELEGRAM_BOT_TOKEN = '7487760533:AAGVGIPtX4OHO4YwBliynTirqVlYPn-bnCY'
TELEGRAM_CHAT_ID = '162433655'

# Configurazione del logging
logging.basicConfig(level=logging.DEBUG)  # Configura il logging per visualizzare i messaggi di debug

# Funzione per verificare se un file ha un'estensione consentita
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Funzione per inviare un messaggio a Telegram
def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    requests.post(url, data=data)

# Funzione per ottenere l'indirizzo IP pubblico del server
def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json')
        data = response.json()
        return data.get('ip', 'Unknown IP')
    except Exception as e:
        logging.error(f"Error fetching public IP: {e}")
        return 'Unknown IP'

# Funzione per ottenere informazioni sul paese dell'indirizzo IP
def get_ip_info(ip):
    try:
        response = requests.get(f'https://ipinfo.io/{ip}/json')
        data = response.json()
        country = data.get('country', 'Unknown Country')
        return country
    except Exception as e:
        logging.error(f"Error fetching IP info: {e}")
        return 'Unknown Country'

# Funzione per ottenere informazioni sul client
def get_client_info(status):
    ip = get_public_ip()  # Ottiene l'IP pubblico
    country = get_ip_info(ip)  # Ottiene informazioni sul paese
    system_info = platform.system() + ' ' + platform.release()  # Ottiene informazioni sul sistema operativo
    message = (
        f"Access Alert!\n"
        f"Status: {status}\n"
        f"IP Address: {ip}\n"
        f"Country: {country}\n"
        f"System Info: {system_info}"
    )
    return message

# Funzione per inviare un messaggio di successo a Telegram
def send_success_message(action, details=''):
    message = (
        f"Success!\n"
        f"Action: {action}\n"
        f"Details: {details}\n"
        f"{get_client_info(status='')}"  # Include informazioni sul client
    )
    send_telegram_message(message)

# Funzione eseguita prima di ogni richiesta
@app.before_request
def log_login_and_failed_authentication():
    if request.endpoint not in ['static', 'download_shared_files']:
        if not basic_auth.authenticate():
            if 'has_logged_in' in session:
                del session['has_logged_in']
            message = get_client_info(status='Failed Login Attempt')
            send_telegram_message(message)
        elif basic_auth.authenticate() and 'has_logged_in' not in session:
            send_success_message('Successful Login')
            session['has_logged_in'] = True

# Rotta principale dell'applicazione, visibile solo agli utenti autenticati
@app.route('/')
@basic_auth.required
def index():
    return render_template('index.html', files=get_files(''), current_path='', parent_path='')

# Rotta per visualizzare una directory specifica
@app.route('/view/<path:subpath>')
@basic_auth.required
def view_directory(subpath):
    return render_template('index.html', files=get_files(subpath), current_path=subpath, parent_path=os.path.dirname(subpath))

# Rotta per caricare i file
@app.route('/upload', methods=['POST'])
@basic_auth.required
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    files = request.files.getlist('file')  # Ottiene i file dal modulo
    current_path = request.form['current_path']  # Ottiene il percorso corrente dal modulo
    for file in files:
        if file.filename == '':
            return 'No selected file'
        if file and allowed_file(file.filename):  # Verifica se il file è valido
            filename = secure_filename(file.filename)  # Sicurezza del nome del file
            upload_dir = os.path.join(UPLOAD_FOLDER, current_path)  # Percorso di upload
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)  # Crea la cartella di upload se non esiste
            file.save(os.path.join(upload_dir, filename))  # Salva il file
            send_success_message('File Upload', f"File: {filename}\nPath: {current_path}")  # Invia messaggio di successo
    return redirect(url_for('view_directory', subpath=current_path))  # Redirect alla directory corrente

# Rotta per eliminare un file o una directory
@app.route('/delete/<string:file_type>/<path:filename>', methods=['GET', 'POST'])
@basic_auth.required
def delete_file(file_type, filename):
    current_path = request.args.get('current_path', '')  # Ottiene il percorso corrente dalla query string
    file_path = os.path.join(UPLOAD_FOLDER, current_path, filename)  # Percorso del file o directory da eliminare
    if file_type == 'directory' and os.path.isdir(file_path):
        shutil.rmtree(file_path)  # Elimina la directory
        send_success_message('Directory Deleted', f"Directory: {filename}\nPath: {current_path}")
    elif file_type == 'file' and os.path.isfile(file_path):
        os.remove(file_path)  # Elimina il file
        send_success_message('File Deleted', f"File: {filename}\nPath: {current_path}")
    else:
        return 'File or directory not found'
    return redirect(url_for('view_directory', subpath=current_path))  # Redirect alla directory corrente

# Rotta per scaricare un file
@app.route('/download/<path:filename>')
@basic_auth.required
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)  # Invia il file come allegato

import os
import zipfile

# Rotta per condividere un file o una directory
@app.route('/share/<path:filename>', methods=['GET'])
@basic_auth.required
def share_file(filename):
    current_path = request.args.get('current_path', '')  # Ottiene il percorso corrente dalla query string
    file_path = os.path.join(UPLOAD_FOLDER, current_path, filename)  # Percorso del file o directory da condividere
    
    if not os.path.exists(file_path):
        return 'File o cartella non trovata', 404  # Verifica se il file esiste

    share_id = str(uuid.uuid4())  # Genera un ID unico per il link di condivisione
    shared_link_info = {
        'path': os.path.join(current_path, filename),
        'is_directory': os.path.isdir(file_path)  # Verifica se è una directory
    }

    if shared_link_info['is_directory']:
        zip_filename = f"{filename}.zip"  # Nome del file ZIP
        zip_filepath = os.path.join(UPLOAD_FOLDER, zip_filename)  # Percorso del file ZIP
        
        # Compressione della directory
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calcola il percorso relativo per il file ZIP
                    relative_path = os.path.relpath(file_path, start=UPLOAD_FOLDER)
                    zipf.write(file_path, arcname=relative_path)

                # Facoltativamente includere le directory vuote
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    # Calcola il percorso relativo per la directory ZIP
                    relative_path = os.path.relpath(dir_path, start=UPLOAD_FOLDER)
                    zipf.write(dir_path + '/', arcname=relative_path + '/')

        # Aggiorna le informazioni sul link condiviso per puntare al file ZIP
        shared_link_info['path'] = zip_filename
        shared_link_info['is_directory'] = False

    # Salva le informazioni sul link condiviso
    with shelve.open('shared_links.db') as db:
        db[share_id] = shared_link_info

    # Genera l'URL con l'ID di condivisione
    shared_file_url = url_for('shared_file_view', share_id=share_id, _external=True)
    
    send_success_message('File Condiviso', f'File o cartella "{filename}" è stata condivisa.\nLink: {shared_file_url}')
    
    return shared_file_url, 200

# Rotta per visualizzare un file condiviso
@app.route('/shared/<share_id>', methods=['GET'])
def shared_file_view(share_id):
    try:
        with shelve.open('shared_links.db') as db:
            if share_id not in db:
                return 'Link non trovato', 404  # Verifica se l'ID di condivisione esiste

            link_info = db[share_id]
            file_path = os.path.join(UPLOAD_FOLDER, link_info['path'])
            
            logging.debug(f"Accessing file path: {file_path}")
            
            if link_info['is_directory']:
                # Lista tutti i file nella directory
                files = []
                for root, _, filenames in os.walk(file_path):
                    for filename in filenames:
                        relative_path = os.path.relpath(os.path.join(root, filename), UPLOAD_FOLDER)
                        files.append(relative_path)
                return render_template('shared_file_list.html', files=files, share_id=share_id)

            elif os.path.isfile(file_path):
                # Serve il file direttamente
                return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), as_attachment=True)

            return 'File non trovato', 404

    except Exception as e:
        logging.error(f'Errore nel download del file condiviso: {str(e)}')
        return f'Errore nel download del file condiviso: {str(e)}', 500

# Rotta per scaricare i file condivisi
@app.route('/download_shared/<share_id>/<filename>')
def download_shared_files(share_id, filename):
    try:
        with shelve.open('shared_links.db') as db:
            if share_id not in db:
                return 'Link non trovato', 404  # Verifica se l'ID di condivisione esiste

            link_info = db[share_id]
            file_path = os.path.join(UPLOAD_FOLDER, link_info['path'])
            file_to_download = os.path.join(file_path, filename)
            
            logging.debug(f"Downloading file: {file_to_download}")
            
            if os.path.isfile(file_to_download):
                return send_from_directory(file_path, filename, as_attachment=True)

            return 'File non trovato', 404

    except Exception as e:
        logging.error(f'Errore nel download del file condiviso: {str(e)}')
        return f'Errore nel download del file condiviso: {str(e)}', 500

# Funzione per ottenere la lista dei file e directory in una directory
def get_files(subpath):
    directory = os.path.join(UPLOAD_FOLDER, subpath)
    files = []
    with os.scandir(directory) as it:
        for entry in it:
            files.append({
                'name': entry.name,
                'type': 'directory' if entry.is_dir() else 'file'
            })
    return sorted(files, key=lambda x: x['name'])

# Avvio del server Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Avvia il server su tutte le interfacce di rete sulla porta 5000
