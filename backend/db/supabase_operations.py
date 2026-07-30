import os 
import supabase 
from supabase import create_client
import logging 
backend_server = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

logger= logging.getLogger(__name__)



def save_conversation(thread_id, user_msg, bot_response):
    '''
    saves the user question and bot response to the thread id in supabase 

    the conversation is saved with user first, then bot. Easier for retrieval 
    '''
    if not thread_id or not user_msg or not bot_response:
        raise ValueError("One of the parameters is empty")
    
    backend_server.table("conversations").insert([
        {"thread_id": thread_id, "role": "user", "content": user_msg},
        {"thread_id": thread_id, "role": "assistant", "content": bot_response}
    ]).execute()     


def get_full_history(thread_id):
    ''' 
    return the full history without pagination 
    '''
    return backend_server.table("conversations") \
        .select("role, content, created_at") \
        .eq("thread_id", thread_id) \
        .order("created_at") \
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
        .order("created_at") \
        .range(start_index, end_index) \
        .execute().data