'''
main driver file for asking user and generating response
'''
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging

from langgraph.checkpoint.postgres import PostgresSaver
from dev.gemini import create_model, build_advising_graph, generate_response_stream
from backend.supabase_connect import save_conversation
from deployment.utils import print_welcome_message, print_goodbye_message, setup_logging
from pinecone_utility.search import process

logger= logging.getLogger(__name__)

def deploy():
    parser = argparse.ArgumentParser(
        prog='CLI for Advising Bot',
        description="Takes in queries and returns an answer based on the provided context",
    )
    parser.add_argument('--verbose', action='store_true', help="Enable verbose logging output")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

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
            print_welcome_message() 
            user_input = input("\nEnter Your Questions: ")
            user_input_processed= user_input.strip()
            if not user_input_processed:
                continue 
            if user_input_processed.lower() in ['e', 'exit', 'quit']:
                print_goodbye_message() 
                break

            model_response = process(user_input_processed, advising_app=advising_app, thread_id=thread_id)
            # save response to supabase 
            save_conversation(thread_id, user_input, model_response)

if __name__ == "__main__":
    deploy()
