'''
main driver file for asking user and generating response
CLI

    -h
    -
'''
import argparse
import sys
from dev.pinecone_driver import *
from dev.gemini import *
from dev.data_process import *

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

    for chunk in generate_response_stream(
        app=advising_app,
        query=query,
        context_results=pinecone_results,
        thread_id=thread_id,
    ):
        print(chunk, end="", flush=True)

    print("\n")


def main():
    parser = argparse.ArgumentParser(
        prog='CLI for Advising Bot',
        description="Takes in queries and returns an answer based on the provided context",
    )

    # Initial Query
    parser.add_argument('-q', nargs='?')
    args = parser.parse_args()

    model = create_model()
    advising_app = build_advising_graph(model=model, max_messages=8)
    thread_id = "cli-session"

    if args.q:
        # call the process
        process(args.q, advising_app=advising_app, thread_id=thread_id)

    while True:
        user_input = input("\nEnter Your Questions: ")
        user_input= user_input.strip()
        if user_input.lower() in ['e', 'exit', 'quit']:
            print("Exiting Advising Bot. Goodbye!")
            break

        if user_input:
            process(user_input, advising_app=advising_app, thread_id=thread_id)

if __name__ == "__main__":
    main()
