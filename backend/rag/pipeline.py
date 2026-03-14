import sys
import os
from typing import Optional

# Add project root to sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.rag.retriever import VectorStore
from backend.rag.generator import LLMGenerator


def detect_repo(query: str, known_repos: list) -> Optional[str]:
    """
    Detects which repo the query is about by scanning dynamically-loaded repo names.
    Returns the exact repo_name string (as stored in ChromaDB) if found, else None.

    Normalization: underscores, hyphens, and dots are treated as spaces so that
    e.g. 'OpenPLC v3' matches 'OpenPLC_v3' and 'fastapi' matches 'fastapi'.
    """
    def normalize(s):
        return s.lower().replace("_", " ").replace("-", " ").replace(".", " ")

    query_normalized = normalize(query)

    for repo in known_repos:
        if normalize(repo) in query_normalized:
            return repo

    return None  # no specific repo detected → search all


class RAGPipeline:
    def __init__(self):
        print("🚀 Initializing RAG Pipeline...")
        self.retriever = VectorStore()
        self.generator = LLMGenerator()
        print("✅ RAG Pipeline Ready")

    def _get_known_repos(self) -> list:
        """
        Dynamically fetch all repo names indexed in ChromaDB.
        Called fresh on every query so newly-indexed repos are immediately available
        without any code change or backend restart.
        """
        repos = self.retriever.get_all_repo_names()
        if repos:
            print(f"📚 Available repos in ChromaDB: {repos}")
        else:
            print("⚠️ No repos found in ChromaDB yet.")
        return repos

    def run(self, query):
        """
        End-to-end RAG flow:
        1. Dynamically load all indexed repos from ChromaDB
        2. Auto-detect which repo the query targets
        3. Retrieve relevant chunks (filtered by repo if detected)
        4. Generate answer
        """
        print(f"🔄 Processing Query: {query[:100]}")

        # 1. Load repos dynamically — no hardcoded list needed
        known_repos = self._get_known_repos()

        # 2. Auto-detect repo
        repo_name = detect_repo(query, known_repos)
        if repo_name:
            print(f"🎯 Detected repo: {repo_name} — filtering retrieval")
        else:
            print("🌐 No specific repo detected — searching all repos")

        # 3. Retrieve (filtered by repo if detected)
        results = self.retriever.search(query, k=8, repo_name=repo_name)

        if not results['documents'] or not results['documents'][0]:
            # If filtered search found nothing, fall back to all repos
            if repo_name:
                print(f"⚠️ No results for repo '{repo_name}', falling back to all repos")
                results = self.retriever.search(query, k=8, repo_name=None)

        if not results['documents'] or not results['documents'][0]:
            return {
                "answer": "No relevant documents found in the system.",
                "sources": []
            }

        context_chunks = results['documents'][0]
        metadatas = results['metadatas'][0] if results['metadatas'] else []

        # 4. Generate
        answer = self.generator.generate(query, context_chunks)

        # 5. Extract sources — show repo name if available
        sources = [
            m.get("repo_name", m.get("source", "unknown"))
            for m in metadatas
        ]

        return {
            "answer": answer,
            "sources": list(set(sources))   # deduplicate
        }
