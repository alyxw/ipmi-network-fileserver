from flask import Flask, request, send_from_directory, render_template_string, redirect, url_for, Response
import os
import threading
import time
import requests
import io, hashlib, hmac

from urllib.parse import urlparse

app = Flask(__name__)
DOWNLOAD_FOLDER = "./iso"
HASH_FOLDER = "./hash"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(HASH_FOLDER, exist_ok=True)


# Cleanup thread to remove old files
def cleanup_files():
    while True:
        current_time = time.time()
        for file in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, file)
            if os.path.isfile(file_path) and current_time - os.path.getctime(file_path) > 72 * 3600:
                os.remove(file_path)
        for file in os.listdir(HASH_FOLDER):
            file_path = os.path.join(HASH_FOLDER, file)
            if os.path.isfile(file_path) and current_time - os.path.getctime(file_path) > 72 * 3600:
                os.remove(file_path)
        time.sleep(3600)  # Check every hour


threading.Thread(target=cleanup_files, daemon=True).start()


def download_iso(file_url, filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    temp_file_path = file_path + os.urandom(8).hex() + ".part"
    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if (os.path.exists(file_path)):
            file_path, filename = path_deduplicate(filename)
            os.rename(temp_file_path, file_path)
        else:
            os.rename(temp_file_path, file_path)
        # on download completion, generate and store a hash for the file
        with open(file_path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256")
        sha256sum = digest.hexdigest()
        f = open(os.path.join(HASH_FOLDER, filename + ".sha256"), "w")
        f.write(sha256sum)
        f.close()
    except requests.RequestException as e:
        print(f"Download failed for {filename}: {str(e)}")


def path_deduplicate(filename):
    while (os.path.exists(os.path.join(DOWNLOAD_FOLDER, filename))):
        parts = filename.rsplit('.', 1)
        if len(parts) == 1 or parts[1] == '' or len(parts[0]) == 0:
            filename = f"{filename}_{os.urandom(8).hex()}"
        else:
            filename = f"{parts[0]}_{os.urandom(8).hex()}.{parts[1]}"
    return os.path.join(DOWNLOAD_FOLDER, filename), filename


@app.route('/', methods=['GET', 'POST'])
def index():
    with open("index.template.html", "r") as file:
        template = file.read()
    if request.method == 'POST':
        file_url = request.form.get('file_url')
        if not file_url:
            return "No URL provided", 400
        filename = os.path.basename(urlparse(file_url).path)
        threading.Thread(target=download_iso, args=(file_url, filename), daemon=True).start()
        return redirect(url_for('index'))
    return render_template_string(template)


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
            size = os.path.getsize(file_path);

            status = "Ready" if not filename.endswith(".part") else "Downloading..."
            try:
                hash_file = open(os.path.join(HASH_FOLDER, filename + ".sha256"), "r")
                sha256_hash = hash_file.read()
                hash_file.close()
            except:
                if (status == "Downloading..."):
                    sha256_hash = "not yet generated"
                else:
                    sha256_hash = "Error generating hash or not yet finished"

            if (status == "Ready"):
                file_list.append(
                    f"<tr> <td><a href='/iso/{filename}'>{filename}</a></td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")
            else:
                file_list.append(
                    f"<tr> <td>{filename}</td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")

    return "".join(file_list)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8081)
