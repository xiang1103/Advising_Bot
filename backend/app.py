import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langgraph.checkpoint.postgres import PostgresSaver

from backend.llm.factory import create_model
from backend.llm.graph import build_advising_graph, generate_response_stream
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


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: ChatRequest):
    # Run retrieval up front so any pre-stream failure surfaces as a real HTTP 500
    # (the status can no longer be changed once the streaming response has started).
    try:
        index = get_pc_index(INDEX_NAME)
        results = pc_search(index, NAMESPACE, payload.message, top_k=5)
        pinecone_results = retrieve_topk_text(results, top_k=5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def token_generator():
        try:
            for chunk in generate_response_stream(
                app=app.state.advising_app,
                query=payload.message,
                context_results=pinecone_results,
                thread_id=payload.session_id,
            ):
                yield chunk
        except Exception:
            # Streaming has already begun, so we can't change the status code.
            # Emit a trailing marker the client can surface instead of truncating silently.
            yield "\n\n[Advising Bot failed to finish generating this response.]"

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8",
    )