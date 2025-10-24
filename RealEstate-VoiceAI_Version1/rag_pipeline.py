import os
from dotenv import load_dotenv

# Gemini SDKs
import google.generativeai as genai_old  # embeddings
from google import genai as genai_new     # generation
from google.genai import types

# Qdrant
from qdrant_client import QdrantClient

# Cerebras
from cerebras.cloud.sdk import Cerebras

# ----------------------------
# Load environment variables
# ----------------------------
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "voice-agent")

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-4-scout-17b-16e-instruct")

print("CEREBRAS_API_KEY loaded:", bool(CEREBRAS_API_KEY))

# ----------------------------
# Initialize clients
# ----------------------------
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

genai_old.configure(api_key=GEMINI_API_KEY)   # embeddings
gemini_client = genai_new.Client(api_key=GEMINI_API_KEY)  # chat/generation

cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# ----------------------------
# Gemini embeddings
# ----------------------------
def get_gemini_embedding(text: str):
    model = "models/text-embedding-004"
    result = genai_old.embed_content(model=model, content=text)
    return result["embedding"]

# ----------------------------
# Retrieve context from Qdrant
# ----------------------------
def retrieve_context(query: str, top_k: int = 5) -> str:
    query_vec = get_gemini_embedding(query)

    search_result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vec,
        limit=top_k,
        with_payload=True
    )

    return " ".join([hit.payload["text"] for hit in search_result.points])

# ----------------------------
# Conversation history
# ----------------------------
conversation_history = [
    {
        "role": "system",
        "content": (
            "You are a friendly real estate calling agent. "
            "Speak to the customer like you’re on a phone call. "
            "Be short, conversational, and professional. "
            "Do not give all property details at once — only answer "
            "the question and then ask a follow-up question. "
            "Wait for the user to reply before continuing."
        ),
    }
]

# ----------------------------
# Ask Gemini (primary)
# ----------------------------
def ask_gemini(query: str, context: str) -> str | None:
    try:
        # Add conversation context
        conversation_history.append({"role": "user", "content": query})
        conversation_history.append({
            "role": "system",
            "content": f"Property information for reference:\n{context[:800]}"
        })

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=conversation_history,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )

        reply = response.text
        conversation_history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print(f"⚠️ Gemini failed: {e}")
        return None

# ----------------------------
# Ask Cerebras (fallback)
# ----------------------------
def ask_cerebras(query: str, context: str) -> str:
    conversation_history.append({"role": "user", "content": query})
    conversation_history.append({
        "role": "system",
        "content": f"Property information for reference:\n{context[:800]}"
    })

    completion = cerebras_client.chat.completions.create(
        messages=conversation_history,
        model=CEREBRAS_MODEL
    )

    reply = completion.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": reply})
    return reply

# ---------------------------- 
# Orchestrator
# ----------------------------
def answer_query(query: str, top_k: int = 5) -> str:
    context = retrieve_context(query, top_k)

    # Try Gemini
    reply = ask_gemini(query, context)
    if reply:
        print("✅ Gemini reply used")
        return reply

    # Fallback to Cerebras
    print("⚠️ Falling back to Cerebras...")
    return ask_cerebras(query, context)

# ----------------------------
# Manual test
# ----------------------------
if __name__ == "__main__":
    user_q = "Tell me about Amoha project."
    print("User:", user_q)
    bot_reply = answer_query(user_q)
    print("Bot:", bot_reply)
