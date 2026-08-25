'''
all backend functions for managing threads 
'''
import logging 
from fastapi import APIRouter, Request, HTTPException 

from backend.db.supabase_operations import list_all_threads

logger = logging.getLogger(__name__)

# set up middleware router
router= APIRouter(prefix="/threads")

@router.get("")
def get_all_threads():
    '''
    router function for retrieving all threads for display 
    (actual content/history) is retrieved at other functions -> lazy eval
    '''
    pass 