import os
import sys
import json

# ✅ Fix: Suppress HuggingFace tokenizer fork warning (must be set before importing tokenizers)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from kafka import KafkaConsumer
import subprocess
import time
from threading import Lock

# ================= SETUP PATHS =================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

try:
    from rag.retriever import VectorStore
    print("✅ VectorStore module loaded successfully")
except ImportError as e:
    print(f"⚠️ Warning: Could not import VectorStore: {e}")
    VectorStore = None

# ================= KAFKA CONSUMER =================
consumer = KafkaConsumer(
    "rag-upload-events",
    bootstrap_servers="localhost:9092",
    value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else {},
    group_id="rag-consumer-group",   # ✅ Tracks offset between restarts
    auto_offset_reset="latest",      # ✅ On first start, skip old messages
    enable_auto_commit=True
)

print("🔥 Kafka Consumer started. Waiting for messages...")

# ================= BATCH CONTROL =================
EVENT_BUFFER = []
BUFFER_LOCK = Lock()
BATCH_INTERVAL = 5
last_run_time = time.time()

# ================= PROCESSED PATHS (PERSISTENT) =================
PROCESSED_PATHS_FILE = os.path.join(os.path.dirname(__file__), "processed_paths.json")

def load_processed_paths():
    """Load already-processed HDFS paths from disk."""
    if os.path.exists(PROCESSED_PATHS_FILE):
        try:
            with open(PROCESSED_PATHS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"⚠️ Could not load processed paths: {e}")
    return set()

def save_processed_paths(paths):
    """Persist processed HDFS paths to disk."""
    try:
        with open(PROCESSED_PATHS_FILE, "w") as f:
            json.dump(list(paths), f, indent=2)
    except Exception as e:
        print(f"⚠️ Could not save processed paths: {e}")

PROCESSED_PATHS = load_processed_paths()
print(f"📂 Loaded {len(PROCESSED_PATHS)} already-processed paths from disk.")
vector_store = None

# ================= VECTOR STORE INIT =================
if VectorStore:
    try:
        # Absolute path so it works from any working directory
        VECTOR_DB_PATH = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../backend/vector_db")
        )
        vector_store = VectorStore(persist_directory=VECTOR_DB_PATH)
        print(f"✅ ChromaDB Vector Store initialized at: {VECTOR_DB_PATH}")
    except Exception as e:
        print(f"❌ Failed to init Vector Store: {e}")

# ================= HELPERS =================

def read_file_from_hdfs(hdfs_path):
    try:
        result = subprocess.run(
            ["hdfs", "dfs", "-text", hdfs_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="ignore"
        )
        if result.returncode != 0:
            print("❌ HDFS read error:", result.stderr)
            return ""
        return result.stdout
    except Exception as e:
        print("❌ Error reading HDFS file:", e)
        return ""

# ================= INDEXING =================

def run_indexing_job(processed_dir="/rag/processed", repo_name="unknown"):
    if not vector_store:
        print("⚠️ Vector Store not available, skipping indexing.")
        return

    print("🔍 Starting RAG Indexing Job...")

    # Check directory exists
    result = subprocess.run(
        ["hdfs", "dfs", "-ls", processed_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print("❌ Processed directory not found:", result.stderr)
        return

    print("📥 Reading all Spark part files...")

    # ✅ FIX: Read ALL part files at once
    try:
        cmd = f"hdfs dfs -cat {processed_dir}/part-*"
        output = subprocess.check_output(cmd, shell=True)
        content = output.decode("utf-8", errors="ignore")
    except Exception as e:
        print("❌ Error reading processed files:", e)
        return

    if not content:
        print("⚠️ No content found in processed directory.")
        return

    lines = content.splitlines()

    print(f"📦 Total lines (chunks) found: {len(lines)}")

    documents = []
    metadatas = []
    ids = []

    # Each Spark output line = one chunk
    for i, line in enumerate(lines):
        cleaned = line.strip()

        if cleaned:
            documents.append(cleaned)
            metadatas.append({
                "source": "spark_chunk",
                "repo_name": repo_name,   # which repo this chunk came from
                "hdfs_path": processed_dir
            })
            ids.append(f"chunk_{repo_name}_{i}_{int(time.time())}")

    if documents:
        print(f"💾 Indexing {len(documents)} chunks...")

        try:
            BATCH_SIZE = 5000
            total_docs = len(documents)

            for i in range(0, total_docs, BATCH_SIZE):
                batch_docs = documents[i:i + BATCH_SIZE]
                batch_meta = metadatas[i:i + BATCH_SIZE]
                batch_ids = ids[i:i + BATCH_SIZE]

                print(f"📦 Inserting batch {i // BATCH_SIZE + 1} "
                      f"({len(batch_docs)} documents)")

                vector_store.add_documents(batch_docs, batch_meta, batch_ids)

            print("✅ Indexing Complete!")

        except Exception as e:
            print(f"❌ Indexing Failed: {e}")

        print("📂 Processed chunks retained in HDFS for demonstration.")
    else:
        print("⚠️ No valid content extracted to index.")

# ================= SPARK TRIGGER =================

def trigger_scala_preprocessing(
    input_path,
    output_path="hdfs://localhost:9000/rag/processed"
):
    print(f"🚀 Triggering Spark job: {input_path} -> {output_path}")

    check = subprocess.run(
        ["hdfs", "dfs", "-test", "-e", input_path.replace("hdfs://localhost:9000", "")]
    )

    if check.returncode != 0:
        print("❌ Input path does not exist in HDFS. Skipping Spark.")
        return

    spark_cmd = [
        "spark-submit",
        "--master", "spark://172.25.149.20:7077",
        "--deploy-mode", "client",
        "--executor-memory", "1g",
        "--driver-memory", "1g",
        "--total-executor-cores", "2",
        "--conf", "spark.sql.files.ignoreCorruptFiles=true",
        "--conf", "spark.network.timeout=600s",
        "--class", "Preprocessing",
        "/mnt/c/Users/balaj/OneDrive/Desktop/se_project_file/spark/target/scala-2.12/rag-preprocessing-assembly-0.1.jar",
        input_path,
        output_path
    ]

    result = subprocess.run(
        spark_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode == 0:
        print("✅ Spark preprocessing completed successfully")
        # ✅ Mark as done and persist to disk so it survives restarts
        PROCESSED_PATHS.add(input_path)
        save_processed_paths(PROCESSED_PATHS)
        print(f" Saved to processed_paths.json: {input_path}")
        # Extract repo name from HDFS path (e.g. .../repos/thingsboard -> thingsboard)
        extracted_repo = input_path.rstrip("/").split("/")[-1]
        run_indexing_job(processed_dir="/rag/processed", repo_name=extracted_repo)
        return True
    else:
        print("❌ Spark preprocessing failed")
        print("STDERR:", result.stderr)
        return False

# ================= MAIN LOOP =================

while True:
    message_pack = consumer.poll(timeout_ms=1000)
    current_time = time.time()

    for tp, messages in message_pack.items():
        for message in messages:
            event = message.value

            if not event:
                continue

            hdfs_path = event.get("hdfs_path", "").rstrip("/")  # ✅ normalize path
            full_path = f"hdfs://localhost:9000{hdfs_path}"

            # ✅ Skip already-processed paths (checked against persisted set)
            if full_path in PROCESSED_PATHS:
                print(f"⏭️ Skipping already processed: {full_path}")
                continue

            print("📥 Received event:", event)

            with BUFFER_LOCK:
                EVENT_BUFFER.append(event)

    if current_time - last_run_time >= BATCH_INTERVAL:
        print(f"⏳ Batch window reached ({len(EVENT_BUFFER)} events)")

        with BUFFER_LOCK:
            if EVENT_BUFFER:
                completed = []  # track events that finished successfully

                for e in EVENT_BUFFER:
                    if e.get("type") == "file":
                        file_path = e.get("hdfs_path")
                        print("➡ Processing file/repo:", file_path)

                        success = trigger_scala_preprocessing(
                            input_path=f"hdfs://localhost:9000{file_path}"
                        )

                        if success:
                            completed.append(e)  # ✅ Remove only on success

                # Remove only successfully processed events from buffer
                for done in completed:
                    EVENT_BUFFER.remove(done)

                if not completed:
                    print("⚠️ No events were successfully processed this batch.")

        last_run_time = current_time