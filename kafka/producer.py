from kafka import KafkaProducer
import json
import time

# ================= KAFKA PRODUCER =================
producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=3,
    linger_ms=10
)

# 🔴 MUST MATCH CONSUMER TOPIC
TOPIC_NAME = "rag-upload-events"


# ================= PRODUCER HELPERS =================
def send_file_upload_event(hdfs_file_path):
    event = {
        "type": "file",
        "source": "upload",
        "hdfs_path": hdfs_file_path
    }

    try:
        meta = producer.send(TOPIC_NAME, event).get(timeout=10)
        producer.flush()
        print("📤 Sent FILE event:", event)
        print(f"✅ Delivered to {meta.topic}:{meta.partition}")
    except Exception as e:
        print("❌ FILE event failed:", e)


def send_repo_upload_event(hdfs_repo_path, repo_name=None):
    event = {
        "type": "file",
        "source": "git",
        "hdfs_path": hdfs_repo_path
    }

    if repo_name:
        event["repo_name"] = repo_name

    try:
        meta = producer.send(TOPIC_NAME, event).get(timeout=10)
        producer.flush()
        print("📤 Sent REPO event:", event)
        print(f"✅ Delivered to {meta.topic}:{meta.partition}")
    except Exception as e:
        print("❌ REPO event failed:", e)


# ================= TEST DRIVER =================
if __name__ == "__main__":
    print("⚠️ Test producer running (NOT UI driven)")

    # 🔥 ACTUAL EVENT (SYSTEM AWAKENS HERE)
    send_repo_upload_event(
        "/rag/uploads/repos/zephyr",
        "zephyr"
    )

    # Optional file test
    # send_file_upload_event("/rag/uploads/sample.txt")

    print("✅ Test producer finished")
