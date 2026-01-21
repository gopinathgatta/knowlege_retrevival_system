import streamlit as st
import requests

st.set_page_config(page_title="Big Data RAG System", layout="centered")

st.title("📚 Big Data Knowledge Retrieval System")

# ================= FILE UPLOAD =================
st.subheader("📄 Upload Document (PDF / TXT)")

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "txt"])

if uploaded_file and st.button("Upload File"):
    with st.spinner("Uploading file to HDFS..."):
        res = requests.post(
            "http://localhost:5000/upload",
            files={"file": (uploaded_file.name, uploaded_file.getvalue())}
        )
        st.json(res.json())


# ================= GITHUB REPO UPLOAD =================
st.subheader("🧩 Upload GitHub Repository")

repo_url = st.text_input("Enter GitHub Repository URL")

if st.button("Submit Repository"):
    with st.spinner("Processing repository (this may take time)..."):
        res = requests.post(
            "http://localhost:5000/upload_repo",
            json={"repo_url": repo_url}
        )
        st.json(res.json())


# ================= QUERY =================
st.subheader("🤖 Ask a Question")

query = st.text_input("Enter your query")

if st.button("Ask"):
    res = requests.post(
        "http://localhost:5000/query",
        json={"query": query}
    )
    st.write(res.json()["answer"])
