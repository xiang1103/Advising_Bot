import os 
from datetime import datetime, timezone
from supabase import create_client
import logging 

logger= logging.getLogger(__name__)
backend_server = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
logger.info("Supabase connected")



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
    try:
        backend_server.table("conversations").insert([
            {"thread_id": thread_id, "role": "user", "content": user_msg, "created_at":asked_iso},
            {"thread_id": thread_id, "role": "advising_bot", "content": bot_response, "created_at":answered_iso}
        ]).execute()
    except Exception as e: 
        raise RuntimeError(f"Error encountered at saving conversation for thread {thread_id}: {e}")   


def get_full_history(thread_id):
    ''' 
    return the full history without pagination 
    '''
    return backend_server.table("conversations") \
        .select("role, content, created_at") \
        .eq("thread_id", thread_id) \
        .order("created_at") \
        .order("id") \
        .execute().data 

def get_history(thread_id, page_num=1, page_size=10): 
    ''' 
    get past history in the database for pagination 
    Returned from latest created_at to earleist created_at 

    Args: 
        num_messages: number of messages to show  
    
    '''
    start_index =  (page_num-1) * page_size 
    end_index = start_index + page_size-1 

    return backend_server.table("conversations") \
        .select("role, content, created_at") \
        .eq("thread_id", thread_id) \
        .order("created_at", desc=True) \
        .order("id")    \
        .range(start_index, end_index) \
        .execute().data