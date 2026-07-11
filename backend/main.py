"""
YouTube RAG Chatbot — Backend API
Run locally: uvicorn main:app --reload --port 8000

Endpoints:
  POST /load_video  { "video_id": "..." }         -> fetches transcript, builds/loads per-video Chroma collection
  POST /chat         { "video_id": "...", "question": "..." } -> retrieves + generates answer
"""

import os
import re
import glob
import shutil

import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_chroma import Chroma
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint, HuggingFaceEmbeddings

load_dotenv()

# ---------- App setup ----------
app = FastAPI(title="YouTube RAG Chatbot Backend")

# Allow the Chrome extension (and youtube.com content script) to call this API.
# Chrome extensions call from an "chrome-extension://<id>" origin — allow all for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHROMA_ROOT = "./chroma_store"  # each video gets its own persist_directory subfolder

# ---------- Load heavy models ONCE at startup ----------
print("Loading embedding model...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

print("Setting up LLM endpoint...")
llm = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen2.5-7B-Instruct",
    task="text-generation",
    max_new_tokens=512,
    provider="auto",
)
model = ChatHuggingFace(llm=llm)

prompt = PromptTemplate(
    template="""
        You are a helpful assistant answering questions about a YouTube video.
        Answer only from the provided transcript context.
        If the context is insufficient, say you don't know — do not make things up.
        {context}
        Question: {question}
    """,
    input_variables=["context", "question"],
)

# in-memory cache: video_id -> retriever (avoids reprocessing the same video)
retriever_cache: dict[str, object] = {}


# ---------- Transcript fetching (yt-dlp based, same as your script) ----------
def download_captions(video_id: str, lang: str = "en") -> str | None:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "vtt",
        "skip_download": True,
        "outtmpl": f"{video_id}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    matches = glob.glob(f"{video_id}*.vtt")
    return matches[0] if matches else None


def vtt_to_text(vtt_path: str) -> str:
    with open(vtt_path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = raw.splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue
        clean = re.sub(r"<[^>]+>", "", line)
        text_lines.append(clean)

    deduped = []
    for line in text_lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return " ".join(deduped)


def get_transcript(video_id: str) -> str:
    vtt_path = download_captions(video_id)
    if not vtt_path:
        raise RuntimeError("No captions available for this video.")
    transcript = vtt_to_text(vtt_path)
    os.remove(vtt_path)
    return transcript


def build_retriever_for_video(video_id: str):
    """Fetch transcript, chunk, embed, and store in a per-video Chroma collection."""
    persist_dir = os.path.join(CHROMA_ROOT, video_id)

    # If this video was already processed in a previous run, reuse the stored collection.
    if os.path.exists(persist_dir):
        vector_store = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
        )
        return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 4})

    transcript = get_transcript(video_id)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)
    chunks = text_splitter.create_documents([transcript])

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir,
    )
    return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 4})


# ---------- Request schemas ----------
class LoadVideoRequest(BaseModel):
    video_id: str


class ChatRequest(BaseModel):
    video_id: str
    question: str


# ---------- Endpoints ----------
@app.post("/load_video")
def load_video(req: LoadVideoRequest):
    video_id = req.video_id
    if video_id in retriever_cache:
        return {"status": "already_loaded", "video_id": video_id}

    try:
        retriever = build_retriever_for_video(video_id)
        retriever_cache[video_id] = retriever
        return {"status": "loaded", "video_id": video_id}
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process video: {e}")


@app.post("/chat")
def chat(req: ChatRequest):
    video_id = req.video_id
    question = req.question

    if video_id not in retriever_cache:
        # try to build it on the fly if it wasn't pre-loaded
        try:
            retriever_cache[video_id] = build_retriever_for_video(video_id)
        except RuntimeError as e:
            raise HTTPException(status_code=422, detail=str(e))

    retriever = retriever_cache[video_id]
    docs = retriever.invoke(question)
    context_text = "\n\n".join(doc.page_content for doc in docs)
    final_prompt = prompt.invoke({"context": context_text, "question": question})
    answer = model.invoke(final_prompt)
    return {"answer": answer.content}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.delete("/clear_cache")
def clear_cache():
    """Optional: wipe all stored Chroma collections + in-memory cache (useful during dev)."""
    retriever_cache.clear()
    if os.path.exists(CHROMA_ROOT):
        shutil.rmtree(CHROMA_ROOT)
    return {"status": "cleared"}