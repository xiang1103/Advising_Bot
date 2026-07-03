from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.dev.gemini import build_advising_graph, create_model, generate_response_stream
from backend.dev.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


MODEL = create_model()
ADVISING_APP = build_advising_graph(model=MODEL, max_messages=8)
INDEX_NAME = "stonybrook"
NAMESPACE = "SBUBulletin"


def process_and_return_text(query: str, thread_id: str) -> str:
    index = get_pc_index(INDEX_NAME)
    results = pc_search(index, NAMESPACE, query, top_k=5)
    pinecone_results = retrieve_topk_text(results, top_k=5)

    chunks: list[str] = []
    for chunk in generate_response_stream(
        app=ADVISING_APP,
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
            query=payload.message,
            thread_id=payload.session_id,
        )
        return ChatResponse(reply=reply)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc