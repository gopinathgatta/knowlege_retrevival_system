"""
reset_and_reindex.py
--------------------
Run this in WSL BEFORE re-uploading a repo.
It clears the ChromaDB collection so old garbage chunks don't pollute results.

Usage:
    cd /mnt/c/Users/balaj/OneDrive/Desktop/se_project_file/backend
    python reset_and_reindex.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag.retriever import VectorStore

vs = VectorStore()

print(f"📊 Documents currently in ChromaDB: {vs.count()}")
print("🗑️  Clearing all old chunks...")

vs.clear_collection()

print(f"✅ Done. Documents after clear: {vs.count()}")
print("👉 Now re-upload the repo via the UI to trigger fresh Spark preprocessing + indexing.")
