\
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.rag import RAGPipeline

app = FastAPI(title="RAG Summary Bot (Security Reports)")
pipe = RAGPipeline()

class IngestReq(BaseModel):
    paths: List[str] = Field(default_factory=list)

class AskReq(BaseModel):
    question: str
    k: int = 4
    max_words: int = 200

@app.post("/ingest")
def ingest(req: IngestReq):
    paths = req.paths or []
    if not paths:
        from app.rag import RAW_DIR
        paths = [RAW_DIR]
    added, docs = pipe.ingest(paths)
    return {"added_chunks": added, "docs": docs}

@app.post("/ask")
def ask(req: AskReq):
    out = pipe.ask(req.question, k=req.k, max_words=req.max_words)
    return out
