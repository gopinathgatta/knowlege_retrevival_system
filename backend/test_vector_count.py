from rag.retriever import VectorStore

vs = VectorStore(persist_directory="vector_db")

print("Total documents in DB:", vs.count())
