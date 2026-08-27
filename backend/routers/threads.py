'''
all backend functions for managing threads 
'''
import logging 
from fastapi import APIRouter, Request, HTTPException 
from backend.schema import ThreadSummary
from backend.db.supabase_operations import list_all_threads

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