
# WatchMind — YouTube RAG Chatbot 🎬

Ask questions about any YouTube video while you watch it. A Chrome extension injects a chat sidebar next to the video player; a FastAPI backend fetches the transcript, builds a per-video knowledge base, and answers your questions using retrieval-augmented generation (RAG).

## How it works

```
YouTube tab (Chrome extension)
        │
        │  auto-detects video ID, sends to backend
        ▼
FastAPI backend
        │
        ├─ yt-dlp → fetch video transcript
        ├─ LangChain → chunk transcript
        ├─ HuggingFace embeddings → vectorize chunks
        ├─ ChromaDB → store per-video vector collection
        └─ Qwen2.5-7B-Instruct → generate answers from retrieved context
```

- **Auto-detection**: the extension listens for YouTube's SPA navigation events, so switching videos automatically reloads the chatbot with the new video's context.
- **Per-video isolation**: each video gets its own ChromaDB collection, so context never leaks between videos.
- **Broad vs. specific questions**: general questions ("summarize this video") use the full transcript directly; specific questions ("what did they say about X") use similarity-based chunk retrieval.

## Tech stack

| Layer | Tool |
|---|---|
| Transcript extraction | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Chunking & orchestration | [LangChain](https://www.langchain.com/) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | [ChromaDB](https://www.trychroma.com/) |
| LLM | `Qwen2.5-7B-Instruct` (via HuggingFace Inference API) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) |
| Extension | Chrome Manifest V3 |

## Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `backend/.env` file (optional, for higher HuggingFace rate limits):
```
HF_TOKEN=your_huggingface_token
```

Run the server:
```bash
uvicorn main:app --reload --port 8000
```

Verify it's running: open `http://127.0.0.1:8000/health` — should return `{"status":"ok"}`.

### 2. Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` folder

### 3. Use it

With the backend running, open any YouTube video. A sidebar appears automatically, fetches the transcript, and you can start asking questions.

## Project structure

```
.
├── backend/
│   ├── main.py           # FastAPI app: /load_video, /chat, /health endpoints
│   └── requirements.txt
└── extension/
    ├── manifest.json     # Chrome extension config (Manifest V3)
    ├── content.js         # Injects sidebar, detects video changes, calls backend
    └── sidebar.css        # Sidebar styling
```

## Notes

- This runs entirely locally — no paid services required.
- The backend must be running for the extension to work; it's a local-first tool, not a hosted service (yet).
- Transcript fetching depends on YouTube auto-generated captions being available for the video.

## Author

Built by [Ahsaan Jameel](https://github.com/ahsaanjameel595) as part of an ongoing deep dive into LangChain, RAG systems, and applied GenAI engineering.
