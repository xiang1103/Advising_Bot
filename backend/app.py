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
from backend.agent_graph.registry import GraphRegistry, UnknownModelError
from backend.db.error_handler import (
    DatabaseError,
    DatabaseRequestError,
    DatabaseUnavailable,
)
from backend.routers import chat, threads
from backend.utils import setup_logging

# nothing configures the root logger otherwise, and its default level hides
# INFO - including the per-reply model line in agent_graph. verbose=False here
# means ERROR only, which switches those off again
setup_logging(verbose=True)

logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("LANGGRAPH_CHECKPOINT_URL")
    if not db_url:
        raise RuntimeError(
            "LANGGRAPH_CHECKPOINT_URL environment variable is required to enable LangGraph's Postgres checkpointing."
        )

    # Adapter that opens the Postgres connection and keeps it alive for the app lifespan.
    # keep the memory up 
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        # no model is built here: the registry compiles each graph on the first
        # request that selects it, so an unused provider is never instantiated
        # and a broken one only fails the requests that ask for it. Every graph
        # shares this checkpointer, which is what lets a thread change model
        # without losing its memory
        app.state.graph_registry = GraphRegistry(checkpointer=checkpointer, max_messages=8)
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


@app.exception_handler(UnknownModelError)
async def handle_unknown_model(request: Request, exc: UnknownModelError):
    # the client picked a model the server does not serve: retrying it unchanged
    # will not help, so this is a 400 rather than a 500
    logger.warning("Rejected unknown model %r", exc.model_id)
    return JSONResponse(status_code=400, content={"detail": "Unsupported model selection."})



# include different endpoint routers 
app.include_router(chat.router)
app.include_router(threads.router)



@app.get("/health")
def health_check():
    return {"status": "ok"}