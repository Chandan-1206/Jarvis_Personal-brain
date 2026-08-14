"""
Convenience local dev runner.

Usage:
    python run.py

Equivalent to running:
    uvicorn api.index:app --reload

This is for LOCAL DEVELOPMENT ONLY. On Vercel, the deployed app is served
directly from api/index.py via vercel.json — this file is never used in
production.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.index:app", host="127.0.0.1", port=8000, reload=True)
