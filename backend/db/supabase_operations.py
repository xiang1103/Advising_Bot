import os 
from datetime import datetime, timezone
from supabase import create_client
from backend.db.error_handler import db_operation, DatabaseRequestError 
import logging

logger= logging.getLogger(__name__)
backend_server = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
logger.info("Supabase connected")


# --- operations ------------------------------------------------------------

def create_thread_table_entry(id:str, title:str):
    '''
    given a thread id, check if this id already exists in thread datatable or create it 
    '''
    if not id:
        raise DatabaseRequestError(operation="create_thread_table_entry requires a thread id")
    row = {"id": id}
    if title: 
        row["title"] = title 

    with db_operation("create_thread_table_entry"):
        (backend_server.table("threads") 
            .upsert(row, on_conflict="id",ignore_duplicates=True) 
            .execute() 
        )


def save_conversation(thread_id, user_msg, bot_response, ask_time:datetime, answer_time:datetime):
    '''
    saves the user question and bot response to the thread id in supabase 
    the conversation is saved with user first, then bot. Easier for retrieval
    Need to ensure the order of insertion is correct / matches the order 
    '''
    if not thread_id or not user_msg or not bot_response:
        raise ValueError("One of the parameters is empty")
    
    # datetime to make the saving json serializable 
    asked_iso = ask_time.astimezone(timezone.utc).isoformat()
    answered_iso = answer_time.astimezone(timezone.utc).isoformat()

    with db_operation("save_conversation"):
        backend_server.table("conversations").insert([
            {"thread_id": thread_id, "role": "user", "content": user_msg, "created_at":asked_iso},
            {"thread_id": thread_id, "role": "advising_bot", "content": bot_response, "created_at":answered_iso}
        ]).execute()


def list_all_threads(limit=50): 
    '''
    return all the threads in the threads table fo the database, returning as json 
    ''' 
    with db_operation("list_all_threads"):
        return (
            backend_server.table("threads")
                .select("id, title")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute().data
        )

def retrieve_thread_conversation(thread_id:str):
    '''
    retrieve all conversation history from conversations table given the thread id
    ordered oldest first, which is the order the frontend renders bubbles in
    '''
    with db_operation("retrieve_thread_conversation"):
        return (
            backend_server.table("conversations")
                .select("id, role, content")
                .eq("thread_id", thread_id)
                .order("created_at")
                .order("id")
                .execute().data
        )


def get_history(thread_id, page_num=1, page_size=10): 
    ''' 
    get past history in the database for pagination 
    Returned from latest created_at to earleist created_at 

    Args: 
        num_messages: number of messages to show  
    
    '''
    # caught here rather than on the wire: a page_num below 1 becomes a negative
    # OFFSET, which postgres rejects with a 400 after a full round trip
    if page_num < 1 or page_size < 1:
        raise ValueError("page_num and page_size must be >= 1")

    start_index =  (page_num-1) * page_size 
    end_index = start_index + page_size-1 

    with db_operation("get_history"):
        return backend_server.table("conversations") \
            .select("role, content, created_at") \
            .eq("thread_id", thread_id) \
            .order("created_at", desc=True) \
            .order("id")    \
            .range(start_index, end_index) \
            .execute().data
