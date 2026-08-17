'''
entry point program that runs from top to bottom, variable app is imported 
'''

import os
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from backend.agent_graph.langgraph import build_advising_graph
from backend.clients.llm.gemini import create_model
from backend.config import GEMINI_MODEL 
from backend.routers import chat

logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("LANGGRAPH_CHECKPOINT_URL")
    if not db_url:
        raise RuntimeError(
            "LANGGRAPH_CHECKPOINT_URL environment variable is required to enable LangGraph's Postgres checkpointing."
        )

    # create the model 
    model = create_model(GEMINI_MODEL)
    logger.info(f"Model created: {GEMINI_MODEL}")
    # Adapter that opens the Postgres connection and keeps it alive for the app lifespan.
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        app.state.advising_app = build_advising_graph(model=model, max_messages=8).compile(
            checkpointer=checkpointer
        )
        yield

app = FastAPI(lifespan=lifespan)

# allow front end to send HTTP requests over to backend 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include different endpoint routers 
app.include_router(chat.router)



@app.get("/health")
def health_check():
    return {"status": "ok"}