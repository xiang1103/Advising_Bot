from pinecone import Pinecone 


def retrieve_state_from_thread(thread_id: str, app):
    '''
    retreive the history data given a thread id from the in memory saver 
    ''' 
    config = {"configurable": {"thread_id": thread_id}}
    state = app.get_state(config)
    return state 

def retrieve_history_from_state(state):
    if not state: 
        raise ValueError("No input state")
    try: 
        return state.values["messags"]
    except Exception as e: 
        raise RuntimeError(f"Failed to retrieve messages {e}")
        