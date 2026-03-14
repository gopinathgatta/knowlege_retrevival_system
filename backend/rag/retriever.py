import sys
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import chromadb
from chromadb.config import Settings
import os
import sys

# Add project root to sys path to import embeddings
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from embeddings.embed import EmbeddingModel


class VectorStore:
    def __init__(self, persist_directory=None):
        if persist_directory is None:
            # Always resolve relative to THIS file's location, not CWD
            persist_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "vector_db")
            persist_directory = os.path.normpath(persist_directory)
        print(f"📂 VectorStore path: {persist_directory}")
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name="rag_docs")
        self.embedder = EmbeddingModel()

    def add_documents(self, documents, metadatas, ids):
        """
        documents: List[str] - text chunks
        metadatas: List[dict] - e.g. {"source": "filename"}
        ids: List[str] - unique IDs
        """
        print(f"📥 Adding {len(documents)} documents to Vector Store...")
        
        # Embed
        embeddings = self.embedder.embed(documents)
        
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print("✅ Documents added.")

    def search(self, query, k=8, repo_name=None):
        print(f"🔍 Searching for: {query[:80]}...")

        query_embedding = self.embedder.embed(query)[0]

        # Filter by repo if specified — prevents ThingsBoard chunks polluting open62541 queries
        where_filter = {"repo_name": repo_name} if repo_name else None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where_filter
        )

        return results

    def count(self):
        """Returns total number of documents stored in the collection"""
        return self.collection.count()

    def get_all_repo_names(self):
        """
        Returns a sorted list of all unique repo_name values stored in ChromaDB.
        Used by the pipeline to auto-detect repos without a hardcoded list.
        """
        try:
            all_meta = self.collection.get(include=["metadatas"])
            names = set()
            for m in all_meta.get("metadatas", []):
                if m and m.get("repo_name"):
                    names.add(m["repo_name"])
            return sorted(names)
        except Exception as e:
            print(f"⚠️ Could not fetch repo names: {e}")
            return []

    def clear_collection(self):
        """Wipe ALL documents from the collection (use before re-indexing)"""
        self.client.delete_collection(name="rag_docs")
        self.collection = self.client.get_or_create_collection(name="rag_docs")
        print("🗑️ Collection cleared. Ready for fresh indexing.")


if __name__ == "__main__":
    vs = VectorStore()
    vs.add_documents(["This is a test doc"], [{"source": "test"}], ["doc1"])
    print(vs.search("test"))
