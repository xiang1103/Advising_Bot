'''
contains all backend functions used for generating & interacting with chat responses from LLM model
'''
import logging 
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from backend.schema import ChatRequest
from backend.config import INDEX_NAME, NAMESPACE 
from backend.clients.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text
from backend.agent_graph.langgraph import generate_response_stream

logger = logging.getLogger(__name__)
# set up router for all /chat routes 
router = APIRouter(prefix="/chat", tags=["chat"])



def token_generator(request:Request, query:str,pinecone_results:list, thread_id:str):
    '''
    helper function to generate tokens 
    '''
    try:
        for chunk in generate_response_stream(
            app=request.app.state.advising_app,
            query=query,
            context_results=pinecone_results,
            thread_id=thread_id,
        ):
            yield chunk
    except Exception:
        # Streaming has already begun, so we can't change the status code.
        # Emit a trailing marker the client can surface instead of truncating silently.
        yield "\n\n[Advising Bot failed to finish generating this response.]"
 

@router.post("")
def chat(payload: ChatRequest, request:Request):
    '''
    given the app/advising graph as a FastAPI request and the user question, generate response with the chat model 
    '''
    # Run retrieval up front so any pre-stream failure surfaces as a real HTTP 500
    # (the status can no longer be changed once the streaming response has started).
    try:
        index = get_pc_index(INDEX_NAME)
        results = pc_search(index, NAMESPACE, payload.message, top_k=5)
        pinecone_results = retrieve_topk_text(results, top_k=5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    
    return StreamingResponse(
        token_generator(request, query=payload.message,pinecone_results= pinecone_results, thread_id=payload.thread_id),
        media_type="text/plain; charset=utf-8",
    )
