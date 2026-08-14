# /api/index.py
"""
Personal Brain — FastAPI entrypoint.

Vercel's Python runtime treats this file as a serverless function and
serves the ASGI `app` object below for every request routed to it
(see vercel.json). Locally, run with:

    uvicorn api.index:app --reload

then open http://127.0.0.1:8000
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Personal Brain")


@app.get("/api/health")
def health():
    """Basic liveness check — confirms the deployed function is running."""
    return {"status": "ok", "service": "personal-brain"}


@app.get("/", response_class=HTMLResponse)
def home():
    """
    Placeholder landing page. Stage 1 goal is just: this loads, on Vercel,
    with zero errors. The real chat UI replaces this in a later stage.
    """
    return """
    <html>
      <head><title>Personal Brain</title></head>
      <body style="font-family: sans-serif; max-width: 640px; margin: 4rem auto;">
        <h1>🧠 Personal Brain</h1>
        <p>Stage 1 scaffold is live. Chat UI comes in a later stage.</p>
        <p>Health check: <a href="/api/health">/api/health</a></p>
      </body>
    </html>
    """