'''
main driver file for asking user and generating response
CLI

    -h
    -
'''
import argparse
from dev.pinecone_driver import *
from dev.gemini import *
from dev.data_process import *

def process(query, advising_app, thread_id):
    index_name = "stonybrook"   # changed to stonybrook
    namespace = "SBUBulletin"   # changed to SBUBulletin
    index = get_pc_index(index_name)
    query= query
    top_k_num = 5
    results = pc_search(index, namespace, query, top_k_num)
    pinecone_results = retrieve_topk_text(results, top_k_num)
    response = generate_response(
        app=advising_app,
        query=query,
        context_results=pinecone_results,
        thread_id=thread_id,
    )

    msg = response["messages"][-1]
    content = msg.content
    if isinstance(content, list) and content and isinstance(content[0], dict):
        print(content[0].get("text", ""))
    else:
        print(content)

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
        user_input = input("\nEnter Query: ")
        if user_input.strip().lower() in ['e', 'exit', 'quit']:
            print("Exiting Advising Bot. Goodbye!")
            break

        if user_input.strip():
            process(user_input, advising_app=advising_app, thread_id=thread_id)

if __name__ == "__main__":
    main()
