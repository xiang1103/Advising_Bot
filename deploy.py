'''
main driver file for asking user and generating response
CLI
'''
import argparse
import os
import logging

from langgraph.checkpoint.postgres import PostgresSaver
from dev.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text
from dev.gemini import create_model, build_advising_graph, generate_response_stream
from backend.supabase_connect import save_conversation

logging.basicConfig(level=logging.WARNING, force=True)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING) 

def process(query, advising_app, thread_id):
    # connect with pinecone 
    index_name = "stonybrook"   # changed to stonybrook
    namespace = "SBUBulletin"   # changed to SBUBulletin
    index = get_pc_index(index_name)
    top_k_num = 5

    # Fetch from pinecone
    results = pc_search(index, namespace, query, top_k_num)
    pinecone_results = retrieve_topk_text(results, top_k_num)

    print("\nAdvising Bot: ", end="", flush=True)

    full_response =""
    for chunk in generate_response_stream(
        app=advising_app,
        query=query,
        context_results=pinecone_results,
        thread_id=thread_id,
    ):
        print(chunk, end="", flush=True)
        full_response+=chunk 

    print("\n")
    return full_response


def main():
    parser = argparse.ArgumentParser(
        prog='CLI for Advising Bot',
        description="Takes in queries and returns an answer based on the provided context",
    )

    # Initial Query
    thread_id = "user_session" 
    model = create_model()
    workflow = build_advising_graph(model=model, max_messages=8)
    db_url = os.environ.get("DATABASE_URL")

    # open connection to database 
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup() 
        # creates the chat app 
        advising_app= workflow.compile(checkpointer)
        while True:
            user_input = input("\nEnter Your Questions: ")
            user_input_processed= user_input.strip()
            if user_input_processed.lower() in ['e', 'exit', 'quit']:
                print("Exiting Advising Bot. Goodbye!")
                break

            if user_input_processed:
                model_response = process(user_input_processed, advising_app=advising_app, thread_id=thread_id)
                # save response to supabase 
                save_conversation(thread_id, user_input, model_response)

if __name__ == "__main__":
    main()
