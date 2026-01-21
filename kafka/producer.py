from kafka import KafkaProducer
import json
import time

# ================= KAFKA PRODUCER =================
producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

TOPIC_NAME = "upload-events"


# ================= PRODUCER HELPERS =================
def send_file_upload_event(hdfs_file_path):
    """
    Sends file upload event to Kafka
    Matches consumer.py: event["type"] == "file"
    """
    event = {
        "type": "file",
        "hdfs_path": hdfs_file_path
    }

    producer.send(TOPIC_NAME, event)
    producer.flush()

    print("📤 Sent FILE upload event:", event)


def send_repo_upload_event(hdfs_repo_path):
    """
    Sends repo upload event to Kafka
    Matches consumer.py: event["type"] == "repo"
    """
    event = {
        "type": "repo",
        "hdfs_path": hdfs_repo_path
    }

    producer.send(TOPIC_NAME, event)
    producer.flush()

    print("📤 Sent REPO upload event:", event)


# ================= TEST DRIVER =================
if __name__ == "__main__":

    # 🔹 Example 1: File upload event
    send_file_upload_event(
        "/rag/uploads/sample.pdf"
    )

    time.sleep(2)

    # 🔹 Example 2: Repo upload event
    send_repo_upload_event(
        "/rag/uploads/repos/flask"
    )

    print("✅ Events sent successfully")
