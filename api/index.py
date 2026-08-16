"""
Personal Brain -- FastAPI entrypoint.

Vercel Python runtime treats this file as a serverless function and
serves the ASGI `app` object below for every request routed to it
(see vercel.json). Locally, run with:

    python run.py

then open http://127.0.0.1:8000
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brain_reasoning

app = FastAPI(title="Personal Brain")


class ChatRequest(BaseModel):
    message: str
    history: list = []


class ChatResponse(BaseModel):
    answer: str
    history: list


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    answer, updated_history = brain_reasoning.ask(req.message, req.history)
    return ChatResponse(answer=answer, history=updated_history)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "personal-brain"}


@app.get("/", response_class=HTMLResponse)
def home():
    return CHAT_HTML


CHAT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Personal Brain</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 720px;
    margin: 0 auto;
    padding: 1.5rem;
    background: #0f1115;
    color: #e6e6e6;
  }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .subtitle { color: #9a9a9a; font-size: 0.9rem; margin-bottom: 1.5rem; }
  #chat {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-height: 300px;
    margin-bottom: 1rem;
  }
  .msg {
    padding: 0.7rem 1rem;
    border-radius: 12px;
    max-width: 85%;
    line-height: 1.4;
    white-space: pre-wrap;
  }
  .user { align-self: flex-end; background: #2b5cff; color: white; }
  .model { align-self: flex-start; background: #1e2128; border: 1px solid #2a2e37; }
  .loading { align-self: flex-start; color: #9a9a9a; font-style: italic; }
  #input-row { display: flex; gap: 0.5rem; }
  #question {
    flex: 1;
    padding: 0.7rem 1rem;
    border-radius: 10px;
    border: 1px solid #2a2e37;
    background: #1a1d24;
    color: #e6e6e6;
    font-size: 1rem;
  }
  #question:focus { outline: none; border-color: #2b5cff; }
  button {
    padding: 0.7rem 1.2rem;
    border-radius: 10px;
    border: none;
    background: #2b5cff;
    color: white;
    font-size: 1rem;
    cursor: pointer;
  }
  button:disabled { background: #3a3d45; cursor: not-allowed; }
  .examples { margin-top: 1.5rem; font-size: 0.85rem; color: #9a9a9a; }
  .examples span {
    display: inline-block;
    background: #1a1d24;
    border: 1px solid #2a2e37;
    padding: 0.3rem 0.6rem;
    border-radius: 8px;
    margin: 0.2rem 0.3rem 0.2rem 0;
    cursor: pointer;
  }
  .examples span:hover { border-color: #2b5cff; }
</style>
</head>
<body>
  <h1>Personal Brain</h1>
  <div class="subtitle">Ask about your email and Drive files -- it searches and reasons across both.</div>

  <div id="chat"></div>

  <div id="input-row">
    <input id="question" type="text" placeholder="Ask a question..." autocomplete="off" />
    <button id="send">Send</button>
  </div>

  <div class="examples">
    Try:
    <span onclick="ask(this.textContent)">What jobs have I applied to?</span>
    <span onclick="ask(this.textContent)">Did I ever send Vanisha the contract draft, and did she reply?</span>
  </div>

<script>
let history = [];
const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('question');
const sendBtn = document.getElementById('send');

function addMsg(text, cls) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  chatEl.appendChild(div);
  window.scrollTo(0, document.body.scrollHeight);
  return div;
}

async function ask(text) {
  text = text || inputEl.value.trim();
  if (!text) return;
  inputEl.value = '';
  sendBtn.disabled = true;

  addMsg(text, 'user');
  const loadingEl = addMsg('Searching...', 'loading');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: history })
    });
    const data = await res.json();
    loadingEl.remove();
    addMsg(data.answer, 'model');
    history = data.history;
  } catch (err) {
    loadingEl.remove();
    addMsg('Something went wrong: ' + err.message, 'model');
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

sendBtn.addEventListener('click', () => ask());
inputEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
</script>
</body>
</html>
"""
