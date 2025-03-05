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
<style>
    table, th, td {
        border: 1px solid black;
        border-collapse: collapse;
    }

    td {
        padding: 4px
    }
</style>

<p>enter the URL of a file on the internet. it will be downloaded to this and served for use within the IPMI network.
    files will expire and be automatically removed after 3 days.</p>
    <p><b>files uploaded here will be available to anyone on the IPMI network. do not use this to serve sensitive information</b></p>
<form method="post">
    <input type="text" name="file_url" placeholder="Enter URL" required>
    <button type="submit">Download</button>
</form>
<h3>Available Files:</h3>
<table>
    <thead>
    <td>
        <b>Filename</b>
    </td>
    <td>
        <b>Size</b>
    </td>
    <td>
        <b>Status</b>
    </td>
    <td>
        <b>Expiry</b>
    </td>
    <td>
        <b>SHA256 Checksum</b>
    </td>
    </thead>
    <tbody id="file-list">
    </tbody>
</table>
<!--<a href='/iso/{filename}'>{filename}</a> ({round(size / 1000000)}MB) - {status} - Expires in {hours_left}h {minutes_left}m - SHA256: {sha256_hash}-->
<p>for comments, questions and complaints, contact alyx</p>
<h3>other services available</h3>
<ul>
    <!--<li>downloads.dell.com HTTP proxy (port 3355)-->
</ul>
<script>
    function fetchFileList() {
        fetch('/files').then(response => response.text()).then(data => {
            document.getElementById('file-list').innerHTML = data;
        });
    }

    setInterval(fetchFileList, 750);
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
            size = os.path.getsize(file_path);
            sha256_hash = "Not ready..."
            status = "Downloaded" if not filename.endswith(".part") else "Downloading..."
            if (status == "Downloaded"):
                file_list.append(
                    f"<tr> <td><a href='/iso/{filename}'>{filename}</a></td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")
            else:
                file_list.append(
                    f"<tr> <td>{filename}</td> <td>{round(size / 1000000)}MB</td> <td>{status}</td> <td>Expires in {hours_left}h {minutes_left}m</td> <td>{sha256_hash}</td> </tr>")

    return "".join(file_list)


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
    app.run(debug=True, host='0.0.0.0', port=8081)
