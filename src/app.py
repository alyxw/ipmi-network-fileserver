from flask import Flask, request, send_from_directory, render_template_string, redirect, url_for, Response
import os
import threading
import time
import requests
import hashlib
from urllib.parse import urlparse

app = Flask(__name__)
DOWNLOAD_FOLDER = "./iso"
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
            sha256_hash = "Not ready..."  # currently disabled because sha256 sums take too long to generate for large files, need to figure out how to go about caching this. might have to make a separate file containing the sha hash that's generated upon download completion.
            status = "Ready" if not filename.endswith(".part") else "Downloading..."
            if (status == "Ready"):
                file_list.append(
                    f"<tr> <td><a href='/iso/{filename}'>{filename}</a></td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")
            else:
                file_list.append(
                    f"<tr> <td>{filename}</td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")

    return "".join(file_list)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8081)
