from flask import Flask, request, jsonify
import os
import subprocess
from kafka import KafkaProducer
import json
import time

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================
UPLOAD_FOLDER = "uploads"
REPO_FOLDER = "repos"   # kept for structure (not used for storage)
HDFS_UPLOAD_DIR = "/rag/uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPO_FOLDER, exist_ok=True)

KAFKA_TOPIC = "upload-events"
producer = None   # 🔥 Lazy producer


# =========================================================
# INTERNAL: SAFE KAFKA PRODUCER
# =========================================================
def get_kafka_producer():
    global producer
    if producer is None:
        try:
            producer = KafkaProducer(
                bootstrap_servers="localhost:9092",
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                retries=5,
                linger_ms=10
            )
            print("✅ Kafka producer connected")
        except Exception as e:
            print("❌ Kafka not available:", e)
            producer = None
    return producer


# =========================================================
# FILE UPLOAD (PDF / TXT) → LOCAL → HDFS
# =========================================================
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"status": "failed", "message": "No file part"}), 400

    file = request.files["file"]
    local_path = os.path.join(UPLOAD_FOLDER, file.filename)

    file.save(local_path)

    subprocess.run(
        ["hdfs", "dfs", "-mkdir", "-p", HDFS_UPLOAD_DIR],
        check=False
    )

    try:
        subprocess.run(
            ["hdfs", "dfs", "-put", "-f", local_path, HDFS_UPLOAD_DIR],
            check=True
        )
    except subprocess.CalledProcessError:
        return jsonify({"status": "failed", "message": "HDFS upload failed"}), 500

    producer = get_kafka_producer()
    if producer:
        producer.send(KAFKA_TOPIC, {
            "type": "file",
            "filename": file.filename,
            "hdfs_path": f"{HDFS_UPLOAD_DIR}/{file.filename}"
        })
        producer.flush()

    return jsonify({
        "status": "success",
        "filename": file.filename,
        "hdfs_path": f"{HDFS_UPLOAD_DIR}/{file.filename}"
    })


# =========================================================
# INTERNAL FUNCTION (INTENTIONALLY UNUSED)
# =========================================================
def upload_repo_files_to_hdfs(repo_name, repo_path):
    """
    ⚠️ Not used directly.
    Repo ingestion is handled inside /upload_repo itself.
    """
    pass


# =========================================================
# GITHUB REPO UPLOAD → AUTO CLONE → HDFS → KAFKA
# =========================================================
@app.route("/upload_repo", methods=["POST"])
def upload_repo():
    data = request.get_json()
    repo_url = data.get("repo_url")

    if not repo_url:
        return jsonify({"error": "Repository URL missing"}), 400

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    # 🔹 Temp workspace
    temp_dir = f"/tmp/git_ingest_{int(time.time())}"
    repo_path = os.path.join(temp_dir, repo_name)
    hdfs_repo_parent = f"{HDFS_UPLOAD_DIR}/repos"
    hdfs_repo_path = f"{hdfs_repo_parent}/{repo_name}"

    try:
        # 1️⃣ Clone repository
        subprocess.run(
            ["git", "clone", repo_url, repo_path],
            check=True
        )

        # 2️⃣ Ensure HDFS directories exist
        subprocess.run(
            ["hdfs", "dfs", "-mkdir", "-p", hdfs_repo_path],
            check=True
        )

        # 3️⃣ Upload repo CONTENTS (✅ FIXED – NO wildcard error)
        subprocess.run(
            [
                "bash", "-c",
                f"hdfs dfs -put -f {repo_path}/* {hdfs_repo_path}/"
            ],
            check=True
        )

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "failed",
            "message": "Repository ingestion failed",
            "error": str(e)
        }), 500

    finally:
        # 🔥 Cleanup temp directory
        subprocess.run(["rm", "-rf", temp_dir], check=False)

    # 4️⃣ Kafka event
    producer = get_kafka_producer()
    if producer:
        producer.send(KAFKA_TOPIC, {
            "type": "repo",
            "repo_name": repo_name,
            "hdfs_path": hdfs_repo_path
        })
        producer.flush()

    return jsonify({
        "status": "success",
        "message": "Repository uploaded to HDFS and queued for preprocessing",
        "repo": repo_name,
        "hdfs_path": hdfs_repo_path
    })


# =========================================================
# QUERY PLACEHOLDER
# =========================================================
@app.route("/query", methods=["POST"])
def query_handler():
    data = request.get_json()
    query = data.get("query")

    return jsonify({
        "query": query,
        "answer": f"Placeholder answer for: {query}"
    })


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    app.run(port=5000, debug=True)
