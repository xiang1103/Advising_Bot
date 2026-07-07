import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.checkpoint.postgres import PostgresSaver

from backend.src.gemini import build_advising_graph, create_model, generate_response_stream
from backend.pinecone_utility.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text

MODEL = create_model()
INDEX_NAME = "stonybrook"
NAMESPACE = "SBUBulletin"
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required to enable Postgres checkpointing."
        )

    # Adapter that opens the Postgres connection and keeps it alive for the app lifespan.
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        app.state.advising_app = build_advising_graph(model=MODEL, max_messages=8).compile(
            checkpointer=checkpointer
        )
        yield
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic classes for chat entities
class ChatRequest(BaseModel):
    session_id: str
    message: str
class ChatResponse(BaseModel):
    reply: str


def process_and_return_text(advising_app: Any, query: str, thread_id: str) -> str:
    index = get_pc_index(INDEX_NAME)
    results = pc_search(index, NAMESPACE, query, top_k=5)
    pinecone_results = retrieve_topk_text(results, top_k=5)

    chunks: list[str] = []
    for chunk in generate_response_stream(
        app=advising_app,
        query=query,
        context_results=pinecone_results,
        thread_id=thread_id,
    ):
        chunks.append(chunk)

    return "".join(chunks).strip()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        reply = process_and_return_text(
            advising_app=app.state.advising_app,
            query=payload.message,
            thread_id=payload.session_id,
        )
        return ChatResponse(reply=reply)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc