import streamlit as st
import requests

BACKEND_URL = "http://localhost:5000"

st.set_page_config(page_title="Big Data RAG System", layout="centered")
st.title("📚 Big Data Knowledge Retrieval System")

# ================= FILE UPLOAD =================
st.subheader("📄 Upload Document (PDF / TXT)")

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "txt"])

if uploaded_file and st.button("Upload File"):
    with st.spinner("Uploading file to HDFS..."):
        try:
            res = requests.post(
                f"{BACKEND_URL}/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                timeout=60
            )
            if res.ok:
                st.success("✅ File uploaded successfully!")
                st.json(res.json())
            else:
                st.error(f"❌ Upload failed ({res.status_code}): {res.text}")
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to backend. Make sure Flask server is running in WSL.")
        except Exception as e:
            st.error(f"❌ Error: {e}")


# ================= GITHUB REPO UPLOAD =================
st.subheader("🧩 Upload GitHub Repository")

repo_url = st.text_input("Enter GitHub Repository URL")

if st.button("Submit Repository"):
    with st.spinner("Processing repository (this may take time)..."):
        try:
            res = requests.post(
                f"{BACKEND_URL}/upload_repo",
                json={"repo_url": repo_url},
                timeout=300
            )
            if res.ok:
                st.success("✅ Repository queued for processing!")
                st.json(res.json())
            else:
                st.error(f"❌ Failed ({res.status_code}): {res.text}")
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to backend. Make sure Flask server is running in WSL.")
        except Exception as e:
            st.error(f"❌ Error: {e}")


# ================= QUERY =================
st.subheader("🤖 Ask a Question")

query = st.text_input("Enter your query")

if st.button("Ask"):
    if not query.strip():
        st.warning("⚠️ Please enter a question.")
    else:
        with st.spinner("Searching knowledge base..."):
            try:
                res = requests.post(
                    f"{BACKEND_URL}/query",
                    json={"query": query},
                    timeout=120   # 2 min — 70b model can be slow
                )

                if res.ok:
                    try:
                        data = res.json()
                        st.markdown("### 📖 Answer")
                        st.write(data.get("answer", "No answer returned."))

                        sources = data.get("sources", [])
                        if sources:
                            st.markdown("**Sources:**")
                            for s in set(sources):
                                st.markdown(f"- `{s}`")
                    except Exception:
                        st.error(f"❌ Bad response from backend: {res.text[:500]}")
                elif res.status_code == 503:
                    st.error("❌ RAG system is initializing. Please wait a moment and try again.")
                else:
                    st.error(f"❌ Backend error ({res.status_code}): {res.text[:300]}")

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to backend. Make sure Flask server is running in WSL (`python app.py`).")
            except requests.exceptions.Timeout:
                st.error("❌ Request timed out. The model may be overloaded — please try again.")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
