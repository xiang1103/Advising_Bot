'''
all backend functions for managing threads 
'''
import logging
from uuid import UUID
from fastapi import APIRouter, Request, HTTPException
from backend.schema import ThreadSummary, ConversationBlock
from backend.db.supabase_operations import list_all_threads, retrieve_thread_conversation

logger = logging.getLogger(__name__)

# set up middleware router
router= APIRouter(prefix="/threads", tags=["threads"])

@router.get("")
def get_all_threads() -> list[ThreadSummary]:
    '''
    router function for retrieving all threads for display 
    (actual content/history) is retrieved at other functions -> lazy eval
    '''
    try: 
        all_threads = list_all_threads()
        return all_threads 
    except Exception as e:
        logger.exception(f"Exception caught while retrieving threads from database: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve thread history")


@router.get("/{thread_id}/messages")
def get_thread_messages(thread_id: UUID) -> list[ConversationBlock]:
    '''
    router function for retrieving the conversation history of a single thread.
    the sidebar is populated by get_all_threads, this is the lazy second half

    a thread that exists only in the browser (started but never chatted in) has
    no rows yet, so an empty list is a valid answer rather than a 404
    '''
    # the db layer raises DatabaseError subclasses that app.py maps to 503/400/500,
    # so nothing is caught here: swallowing them would flatten a transient outage
    # into an indistinguishable 500
    return retrieve_thread_conversation(str(thread_id))