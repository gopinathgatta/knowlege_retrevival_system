from kafka import KafkaConsumer
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
from threading import Lock

# ================= KAFKA CONSUMER =================
consumer = KafkaConsumer(
    "upload-events",
    bootstrap_servers="localhost:9092",
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    auto_offset_reset="earliest",
    enable_auto_commit=True
)

print("🔥 Kafka Consumer started. Waiting for messages...")

# ================= 🔥 BATCH CONTROL =================
EVENT_BUFFER = []
BUFFER_LOCK = Lock()
BATCH_INTERVAL = 30   # seconds
last_run_time = time.time()

# ================= HELPERS =================
def read_file_from_hdfs(hdfs_path):
    """
    Reads file content from HDFS (NO local storage)
    """
    result = subprocess.run(
        ["hdfs", "dfs", "-cat", hdfs_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="ignore"
    )
    return result.stdout


def trigger_scala_preprocessing():
    """
    🔥 Triggers Scala Spark preprocessing
    Input  : /rag/uploads (files + repos)
    Output : /rag/processed
    """
    print("🚀 Triggering Scala preprocessing job...")

    subprocess.run(
        [
            "spark-submit",
            "--class", "Preprocessing",
            "/mnt/c/Users/balaj/OneDrive/Desktop/se_project_file/spark/preprocessing.jar"
        ],
        check=False
    )


def process_single_repo_file(hdfs_file):
    """
    Process one repo file (future: chunk → embedding)
    """
    content = read_file_from_hdfs(hdfs_file)
    print(f"📄 Repo file: {hdfs_file} | Size: {len(content)} chars")


def process_repo_from_hdfs(hdfs_repo_path):
    """
    Process all repo files in parallel
    """
    print("📂 Scanning repo directory in HDFS:", hdfs_repo_path)

    list_files = subprocess.run(
        ["hdfs", "dfs", "-ls", hdfs_repo_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    hdfs_files = []
    for line in list_files.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 8:
            path = parts[-1]
            if not path.endswith("_SUCCESS"):
                hdfs_files.append(path)

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(process_single_repo_file, hdfs_files)


# ================= MAIN LOOP =================
for message in consumer:
    event = message.value
    print("📥 Received event:", event)

    with BUFFER_LOCK:
        EVENT_BUFFER.append(event)

    current_time = time.time()

    # 🔥 BATCH TRIGGER
    if current_time - last_run_time >= BATCH_INTERVAL:
        print(f"⏳ Batch window reached ({len(EVENT_BUFFER)} events)")

        with BUFFER_LOCK:
            if EVENT_BUFFER:
                for e in EVENT_BUFFER:
                    if e.get("type") == "file" and "hdfs_path" in e:
                        print("➡ Buffered file:", e["hdfs_path"])

                    elif e.get("type") == "repo":
                        if "hdfs_path" in e:
                            print("➡ Buffered repo:", e["hdfs_path"])
                        else:
                            print("⚠️ Skipping legacy repo event:", e)

                # 🔥 ONE Spark run for ALL uploads
                trigger_scala_preprocessing()
                EVENT_BUFFER.clear()

        last_run_time = current_time
