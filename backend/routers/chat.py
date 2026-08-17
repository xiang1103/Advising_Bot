'''
contains all backend functions used for generating & interacting with chat responses from LLM model
'''
import logging 
from datetime import datetime 
from fastapi import APIRouter, Request, HTTPException 
from fastapi.responses import StreamingResponse
from backend.schema import ChatRequest
from backend.config import INDEX_NAME, NAMESPACE, TIMEZONE 
from backend.clients.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text
from backend.agent_graph.langgraph import generate_response_stream
from backend.db.supabase_operations import save_conversation, create_thread_table_entry
from starlette.background import BackgroundTasks

logger = logging.getLogger(__name__)
# set up router for all /chat routes 
router = APIRouter(prefix="/chat", tags=["chat"])



def persist_conversation(thread_id:str, user_message:str, bot_response:list[str], ask_time:datetime): 
    '''
    background job to persist the conversation into the database 
    '''
    if not bot_response:
        return 
    logger.info(f"Saving conversation to {thread_id}")
    full_response = "".join(bot_response)

    # capture answer time to record bot response 
    answered_at = datetime.now(TIMEZONE)
    save_conversation(thread_id=thread_id,user_msg=user_message, bot_response=full_response, ask_time=ask_time, answer_time=answered_at)

def token_generator(request:Request, query:str,pinecone_results:list, thread_id:str, sink:list):
    '''
    helper function to generate tokens and keep track of full response 
    '''
    try:
        for chunk in generate_response_stream(
            app=request.app.state.advising_app,
            query=query,
            context_results=pinecone_results,
            thread_id=thread_id,
        ):
            sink.append(chunk) 
            yield chunk
    except Exception:
        logger.exception("Response failed to generate entirely")
        # when there is an error, immediately terminate 
        yield "\n\n[Advising Bot failed to finish generating this response.]"
        # partial responses are still accpeted, if the connection stops midway, so do not clear sink

@router.post("")
def chat(payload: ChatRequest, request:Request):
    '''
    given the app/advising graph as a FastAPI request and the user question, generate response with the chat model 
    Store the chat response with a background task  
    '''

    # store the asked time for the question 
    asked_at = datetime.now(TIMEZONE) 

    # Run retrieval up front so any pre-stream failure surfaces as a real HTTP 500
    # (the status can no longer be changed once the streaming response has started).
    try:
        index = get_pc_index(INDEX_NAME)
        results = pc_search(index, NAMESPACE, payload.message, top_k=5)
        pinecone_results = retrieve_topk_text(results, top_k=5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("Generating Responses")

    # use a shared by reference list to store all the responses, to be populated  
    collected_convo: list[str] = [] 

    # convert back into string from UUID 
    thread_id = str(payload.thread_id)   
    thread_title = payload.thread_title 

    # create thread table to make sure conversation table is linked with thread  
    create_thread_table_entry(thread_id, thread_title)

    user_message = payload.message 
    
    # create background task for streaming response to run 
    task_save_convo = BackgroundTasks() 
    task_save_convo.add_task(persist_conversation,thread_id=thread_id, user_message=user_message, bot_response = collected_convo, ask_time= asked_at) 

    # stream the response and save the conversation at the end 
    return StreamingResponse(
        token_generator(request, query=user_message,pinecone_results= pinecone_results, thread_id=thread_id, sink=collected_convo),
        media_type="text/plain; charset=utf-8",
        background=task_save_convo
    )

