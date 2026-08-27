'''
entry point program that runs from top to bottom, variable app is imported
'''

import os
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres import PostgresSaver
from backend.agent_graph.langgraph import build_advising_graph
from backend.clients.llm.gemini import create_model
from backend.config import GEMINI_MODEL 
from backend.db.error_handler import (
    DatabaseError,
    DatabaseRequestError,
    DatabaseUnavailable,
)
from backend.routers import chat, threads

logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("LANGGRAPH_CHECKPOINT_URL")
    if not db_url:
        raise RuntimeError(
            "LANGGRAPH_CHECKPOINT_URL environment variable is required to enable LangGraph's Postgres checkpointing."
        )

    # create the model
    model = create_model()
    logger.info(f"Model created: {type(model).__name__}")
    # Adapter that opens the Postgres connection and keeps it alive for the app lifespan.
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        app.state.advising_app = build_advising_graph(model=model, max_messages=8).compile(
            checkpointer=checkpointer
        )
        yield

app = FastAPI(lifespan=lifespan)


# add catch other exceptions 
@app.middleware("http") 
async def catch_unexpected_exceptions(request:Request, call_next):
    '''
    catches exception and manually turn it into a json response 
    '''
    try:
        return await call_next(request)
    except Exception:
        logger.exception(f"Unexpected error on {request.method} at {request.url.path}")
        return JSONResponse(status_code=500, content={"detail": "Internal Error on Unexpected Exception"})


# allow front end to send HTTP requests over to backend 
# all errors raissed by CORS wouldn't propogate down the program 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- error boundary --------------------------------------------------------
# The db layer raises semantic exceptions; this is the single place where they
# become HTTP. Ordering matters: FastAPI dispatches on the exact class, so the
# subclasses are registered alongside the base rather than relying on it

# these error handling catches error that happen at handling request level

def _db_failure(status: int, detail: str, exc: DatabaseError) -> JSONResponse:
    logger.error(
        "%s failed (code=%s): %s", exc.operation, exc.code, exc, exc_info=exc
    )
    return JSONResponse(status_code=status, content={"detail": detail})

@app.exception_handler(DatabaseUnavailable)
async def handle_db_unavailable(request: Request, exc: DatabaseUnavailable):
    # transient: tell the frontend a retry is worth attempting
    return _db_failure(503, "Database temporarily unavailable, please try again.", exc)


@app.exception_handler(DatabaseRequestError)
async def handle_db_request_error(request: Request, exc: DatabaseRequestError):
    # the request itself was rejected, retrying it unchanged will not help
    return _db_failure(400, "Invalid request for this conversation.", exc)


@app.exception_handler(DatabaseError)
async def handle_db_error(request: Request, exc: DatabaseError):
    # our bug or misconfiguration: never leak the driver message to the client
    return _db_failure(500, "Internal error.", exc)



# include different endpoint routers 
app.include_router(chat.router)
app.include_router(threads.router)



@app.get("/health")
def health_check():
    return {"status": "ok"}