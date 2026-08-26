import chromadb
client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection(name="omnia_memory_default")
data = collection.get(include=["metadatas"])
print("Total in get():", len(data["metadatas"]))
