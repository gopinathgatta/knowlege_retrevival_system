from rag.retriever import VectorStore

vs = VectorStore()

results = vs.search("What is Zephyr RTOS?", k=5)

print("Documents Returned:", len(results["documents"][0]))
print(results["documents"][0])

