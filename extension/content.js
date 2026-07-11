// YouTube RAG Chatbot — content script
// Injects a sidebar next to the video player, auto-detects video changes,
// and talks to the local FastAPI backend (http://localhost:8000).

const BACKEND_URL = "http://localhost:8000";

let currentVideoId = null;
let sidebarEl = null;

function getVideoIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("v"); // works for /watch?v=XXXX
}

function createSidebar() {
  if (document.getElementById("yt-rag-sidebar")) return document.getElementById("yt-rag-sidebar");

  const sidebar = document.createElement("div");
  sidebar.id = "yt-rag-sidebar";
  sidebar.innerHTML = `
    <div id="yt-rag-header">
      <span>🎬 Video Chatbot</span>
      <span id="yt-rag-status">idle</span>
    </div>
    <div id="yt-rag-messages"></div>
    <div id="yt-rag-input-row">
      <input id="yt-rag-input" type="text" placeholder="Ask about this video..." />
      <button id="yt-rag-send">Send</button>
    </div>
  `;

  // Append directly to <body> as a fixed-position panel. Inserting next to
  // YouTube's #secondary column is unreliable — that column can be hidden
  // or restructured (theatre mode, narrow windows, layout experiments),
  // which silently hides anything placed inside it.
  document.body.appendChild(sidebar);

  sidebarEl = sidebar;

  sidebar.querySelector("#yt-rag-send").addEventListener("click", sendQuestion);
  sidebar.querySelector("#yt-rag-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendQuestion();
  });

  return sidebar;
}

function setStatus(text) {
  const status = document.getElementById("yt-rag-status");
  if (status) status.textContent = text;
}

function addMessage(role, text) {
  const messages = document.getElementById("yt-rag-messages");
  if (!messages) return;
  const bubble = document.createElement("div");
  bubble.className = `yt-rag-msg yt-rag-${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

async function loadVideo(videoId) {
  setStatus("loading transcript...");
  const messages = document.getElementById("yt-rag-messages");
  if (messages) messages.innerHTML = "";
  addMessage("system", "Loading this video's transcript... this can take a bit the first time.");

  try {
    const res = await fetch(`${BACKEND_URL}/load_video`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    setStatus("ready");
    addMessage("system", "Ready! Ask me anything about this video.");
  } catch (e) {
    setStatus("error");
    addMessage("system", `Could not load this video: ${e.message}. Is the backend running on localhost:8000?`);
  }
}

async function sendQuestion() {
  const input = document.getElementById("yt-rag-input");
  const question = input.value.trim();
  if (!question || !currentVideoId) return;

  addMessage("user", question);
  input.value = "";
  setStatus("thinking...");

  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: currentVideoId, question }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    addMessage("bot", data.answer);
    setStatus("ready");
  } catch (e) {
    addMessage("system", `Error: ${e.message}`);
    setStatus("error");
  }
}

function handleVideoChange() {
  const videoId = getVideoIdFromUrl();
  if (!videoId || videoId === currentVideoId) return;

  currentVideoId = videoId;
  createSidebar();
  loadVideo(videoId);
}

// Initial load
handleVideoChange();

// YouTube is a single-page app — it fires this event on client-side navigation
// (e.g. clicking a related video) instead of a full page reload.
document.addEventListener("yt-navigate-finish", handleVideoChange);

// Fallback: some navigations don't fire yt-navigate-finish reliably,
// so also poll the URL periodically as a safety net.
setInterval(handleVideoChange, 2000);