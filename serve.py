from flask import Flask, request, send_from_directory, render_template_string, redirect, url_for, Response
import os
import threading
import time
import requests
import hashlib
from urllib.parse import urlparse

app = Flask(__name__)
DOWNLOAD_FOLDER = "./iso_files"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# Cleanup thread to remove old files
def cleanup_files():
    while True:
        current_time = time.time()
        for file in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, file)
            if os.path.isfile(file_path) and current_time - os.path.getctime(file_path) > 72 * 3600:
                os.remove(file_path)
        time.sleep(3600)  # Check every hour


threading.Thread(target=cleanup_files, daemon=True).start()


def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        return "Calculating..."


def download_iso(file_url, filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    temp_file_path = file_path + ".part"
    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        os.rename(temp_file_path, file_path)
    except requests.RequestException as e:
        print(f"Download failed for {filename}: {str(e)}")


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file_url = request.form.get('file_url')
        if not file_url:
            return "No URL provided", 400

        filename = os.path.basename(urlparse(file_url).path)

        # Start downloading the file in a background thread
        threading.Thread(target=download_iso, args=(file_url, filename), daemon=True).start()

        return redirect(url_for('index'))

    return render_template_string('''
        <!doctype html>
        <title>alyx's cool ipmi network file hosting</title>
        <h1>alyx's cool ipmi network file hosting</h1>
        <p>enter the URL of a file on the internet. it will be downloaded to this and served for use within the IPMI network. files will expire and be automatically removed after 3 days.</p>
        <form method="post">
            <input type="text" name="file_url" placeholder="Enter URL" required>
            <button type="submit">Download</button>
        </form>
        <h3>Available Files:</h3>
        <div id="file-list"></div>
        
        <p>for comments, questions and complaints, contact alyx</p>
        <script>
            function fetchFileList() {
                fetch('/files').then(response => response.text()).then(data => {
                    document.getElementById('file-list').innerHTML = data;
                });
            }
            setInterval(fetchFileList, 5000);
            fetchFileList();
        </script>
    ''')


@app.route('/files')
def file_list():
    file_list = []
    current_time = time.time()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            timestamp = os.path.getctime(file_path)
            time_remaining = max(0, 72 * 3600 - (current_time - timestamp))
            hours_left = int(time_remaining // 3600)
            minutes_left = int((time_remaining % 3600) // 60)
            sha256_hash = calculate_sha256(file_path) if not filename.endswith(".part") else "Calculating..."
            status = "Downloaded" if not filename.endswith(".part") else "Downloading..."
            file_list.append(
                f"<a href='/iso/{filename}'>{filename}</a> - {status} - Expires in {hours_left}h {minutes_left}m - SHA256: {sha256_hash}")

    return "<br>".join(file_list)


@app.route('/iso/<filename>')
def serve_iso(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return "File not found", 404

    def generate():
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return Response(generate(), headers={
        "Content-Disposition": f"attachment; filename={filename}",
        "Accept-Ranges": "bytes",
        "Content-Type": "application/octet-stream"
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6999)
