import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from research_engine import run_agent_research, OPENAI_MODEL, client

app = FastAPI(title="Meridian Research Agent API")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
extra_origins = os.getenv("ALLOWED_ORIGINS", "")
if extra_origins:
    allowed_origins.extend(
        origin.strip() for origin in extra_origins.split(",") if origin.strip()
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.(vercel\.app|netlify\.app)$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchQuery(BaseModel):
    query: str


@app.post("/api/research")
def handle_research(req: ResearchQuery):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    print(f"⚡ [Research Request] Query: {query}")
    try:
        result = run_agent_research(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "data": result}


@app.get("/api/health")
def health():
    return {"status": "running", "model": OPENAI_MODEL, "llm_enabled": client is not None}
