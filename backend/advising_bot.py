'''
main driver file for asking user and generating response
'''
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging

from langgraph.checkpoint.postgres import PostgresSaver
from backend.llm.factory import create_model
from backend.llm.graph import build_advising_graph, generate_response
from backend.db.supabase_connect import save_conversation
from backend.utils import print_welcome_message, print_goodbye_message, setup_logging
from backend.pinecone_utility.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text

logger= logging.getLogger(__name__)
PC_INDEX_NAME = "stonybrook"
PC_NAMESPACE = "SBUBulletin"
PC_TOP_K= 5
THREAD_ID = "user_session"

def deploy():
    parser = argparse.ArgumentParser(
        prog='CLI for Advising Bot',
        description="Takes in queries and returns an answer based on the provided context",
    )
    parser.add_argument('--verbose', action='store_true', help="Enable verbose logging output")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    # Initial Query
    model = create_model()
    logger.info("Building workflow graph")
    workflow = build_advising_graph(model=model, max_messages=8)
    db_url = os.environ.get("DATABASE_URL")

    # connect to pinecone (default parameter names)
    pc_index = get_pc_index(PC_INDEX_NAME)

    # open connection to database
    logger.info("Connecting to server")
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        # creates the chat app
        logger.info("Creating Advising Bot")
        advising_bot= workflow.compile(checkpointer)
        print_welcome_message()
        while True:
            user_input = input("\nEnter Your Questions: ")
            user_input_processed= user_input.strip()
            if not user_input_processed:
                continue
            if user_input_processed.lower() in ['e', 'exit', 'quit']:
                print_goodbye_message()
                break
            # search at pinecone
            pc_results = pc_search(pc_index, PC_NAMESPACE, user_input_processed, PC_TOP_K)
            pc_results = retrieve_topk_text(pc_results,PC_TOP_K)

            # generate model response
            model_response = generate_response(advising_bot,
                                               user_input_processed,
                                                pc_results,
                                                THREAD_ID)

            # save response to supabase
            save_conversation(THREAD_ID, user_input, model_response)
            logger.info("Conversation saved")

if __name__ == "__main__":
    deploy()


