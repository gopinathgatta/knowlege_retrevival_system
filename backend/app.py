from flask import Flask, request, jsonify
import os
import subprocess
from kafka import KafkaProducer
import json
import time
import shutil
import atexit
from werkzeug.utils import secure_filename  # ✅ Added

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================
UPLOAD_FOLDER = "uploads"
REPO_FOLDER = "repos"
HDFS_UPLOAD_DIR = "/rag/uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPO_FOLDER, exist_ok=True)

KAFKA_TOPIC = "rag-upload-events"
producer = None


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
            print("❌ Kafka producer connection failed:", e)
            producer = None
    return producer


def close_producer():
    global producer
    if producer:
        producer.close()
        print("🔒 Kafka producer closed")


atexit.register(close_producer)


# =========================================================
# HELPER: HDFS COMMANDS (FIXED)
# =========================================================
def run_hdfs_command(args):
    """
    Executes HDFS commands safely on Windows/Linux.
    """
    cmd = ["hdfs", "dfs"] + args

    print(f"🔹 Executing: {' '.join(cmd)}")

    # ✅ IMPORTANT FIX: shell=False (prevents space issues)
    result = subprocess.run(
        cmd,
        check=False,
        shell=False,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"⚠️ HDFS Command Failed: {result.stderr}")
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr
        )

    return result.stdout


# =========================================================
# FILE UPLOAD (PDF / TXT) → LOCAL → HDFS
# =========================================================
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"status": "failed", "message": "No file part"}), 400

    file = request.files["file"]

    # ✅ Sanitize filename (prevents space & weird char issues)
    filename = secure_filename(file.filename)

    local_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, filename))
    file.save(local_path)

    try:
        files_dir = f"{HDFS_UPLOAD_DIR}/files"
        run_hdfs_command(["-mkdir", "-p", files_dir])
        run_hdfs_command(["-put", "-f", local_path, files_dir])
    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "failed",
            "message": "HDFS upload failed",
            "error": str(e)
        }), 500

    producer = get_kafka_producer()
    if producer:
        producer.send(KAFKA_TOPIC, {
            "type": "file",
            "source": "upload",
            "filename": filename,
            "hdfs_path": f"{files_dir}/{filename}"
        })
        producer.flush()
    else:
        print("⚠️ Kafka producer not available, event not sent")

    return jsonify({
        "status": "success",
        "filename": filename,
        "hdfs_path": f"{files_dir}/{filename}"
    })


# =========================================================
# GITHUB REPO UPLOAD → AUTO CLONE → HDFS → KAFKA
# =========================================================
@app.route("/upload_repo", methods=["POST"])
def upload_repo():
    data = request.get_json(force=True, silent=True)

    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    repo_url = data.get("repo_url")
    if not repo_url:
        return jsonify({"error": "Repository URL missing"}), 400

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    temp_dir = os.path.join(os.getcwd(), "temp_git_ingest_" + str(int(time.time())))
    repo_path = os.path.join(temp_dir, repo_name)
    hdfs_repo_path = f"{HDFS_UPLOAD_DIR}/repos/{repo_name}"

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, repo_path],
            check=True,
            shell=(os.name == 'nt')
        )

        run_hdfs_command(["-mkdir", "-p", hdfs_repo_path])

        # ✅ Keep original logic (does NOT affect repo behavior)
        run_hdfs_command(["-put", "-f", repo_path, hdfs_repo_path])

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "failed",
            "message": "Repository ingestion failed",
            "error": str(e)
        }), 500

    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"⚠️ Failed to clean up temp dir {temp_dir}: {e}")

    producer = get_kafka_producer()
    if producer:
        producer.send(KAFKA_TOPIC, {
            "type": "file",
            "source": "git",
            "repo_name": repo_name,
            "hdfs_path": f"{hdfs_repo_path}/{repo_name}"
        })
        producer.flush()
    else:
        print("⚠️ Kafka producer not available, repo event not sent")

    return jsonify({
        "status": "success",
        "message": "Repository uploaded to HDFS and queued for preprocessing",
        "repo": repo_name,
        "hdfs_path": f"{hdfs_repo_path}/{repo_name}"
    })


# =========================================================
# RAG PIPELINE
# =========================================================
import traceback
from rag.pipeline import RAGPipeline

try:
    rag_pipeline = RAGPipeline()
except Exception as e:
    print(f"❌ Failed to initialize RAG Pipeline: {e}")
    traceback.print_exc()
    rag_pipeline = None


# =========================================================
# QUERY ENDPOINT
# =========================================================
@app.route("/query", methods=["POST"])
def query_handler():
    data = request.get_json()
    query = data.get("query") if data else None

    if not query:
        return jsonify({"error": "No query provided"}), 400

    if not rag_pipeline:
        return jsonify({
            "answer": "RAG System is initializing or failed to load. Check logs."
        }), 503

    result = rag_pipeline.run(query)

    return jsonify({
        "query": query,
        "answer": result["answer"],
        "sources": result["sources"]
    })


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    app.run(port=5000, debug=False, use_reloader=False)
