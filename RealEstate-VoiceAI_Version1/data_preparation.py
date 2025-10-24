import os
import requests
import trafilatura
import yaml
from dotenv import load_dotenv
import google.generativeai as genai
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# ----------------------------
# Load env + config
# ----------------------------
load_dotenv()

with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

APP_CFG = CONFIG["app"]

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ----------------------------
# Init Gemini Embeddings
# ----------------------------
def get_gemini_embedding(text: str):
    genai.configure(api_key=GOOGLE_API_KEY)
    model = "models/text-embedding-004"
    result = genai.embed_content(model=model, content=text)
    return result["embedding"]

# ----------------------------
# Crawl & Extract Text
# ----------------------------
def scrape_site(url: str) -> str:
    print(f"🌐 Fetching: {url}")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    downloaded = trafilatura.extract(r.text, include_comments=False)
    return downloaded or ""

# ----------------------------
# Chunk text
# ----------------------------
def chunk_text(text: str, chunk_size: int, overlap: int):
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

# ----------------------------
# Main pipeline
# ----------------------------
def run_indexing():
    print("🔹 Connecting to Qdrant...")
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    collections = [c.name for c in qdrant.get_collections().collections]
    collection_name = APP_CFG["qdrant_collection_name"]

    if collection_name not in collections:
        print(f"📦 Creating new collection: {collection_name}")
        vector_size = len(get_gemini_embedding("test"))
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance="Cosine"),
        )
    else:
        print(f"ℹ️ Collection {collection_name} already exists")

    all_chunks = []
    for url in APP_CFG["start_urls"]:
        text_data = scrape_site(url)
        if text_data:
            chunks = chunk_text(
                text_data,
                APP_CFG["chunking"]["chunk_size"],
                APP_CFG["chunking"]["chunk_overlap"],
            )
            all_chunks.extend(chunks)

    print(f"📦 Total chunks: {len(all_chunks)}")

    points = []
    for idx, chunk in enumerate(all_chunks):
        embedding = get_gemini_embedding(chunk)
        points.append(
            qmodels.PointStruct(
                id=idx,
                vector=embedding,
                payload={"text": chunk, "source": "web"},
            )
        )

    qdrant.upsert(collection_name=collection_name, points=points)
    print(f"✅ Indexed {len(points)} chunks into Qdrant.")

# ----------------------------
# Trigger only when run
# ----------------------------
if __name__ == "__main__":
    run_indexing()
