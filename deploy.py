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

def process(query):
    index_name =  "advising-bot"
    namespace = "bulletin"
    index = get_pc_index(index_name)
    query= query
    results = pc_search(index, namespace, query, 2)
    pinecone_results = retrieve_topk_text(results, 2)
    prompt = create_prompt(pinecone_results, query)
    response = generate_response(prompt)

    print(response.text)

def main():
    parser = argparse.ArgumentParser(
        prog='CLI for Advising Bot',
        description="Takes in queries and returns an answer based on the provided context",
    )

    parser.add_argument('-q', nargs='?')
    args = parser.parse_args()

    # Check the query
    print(args.q)

    if args.q:
        # call the process
        process(args.q)

if __name__ == "__main__":
    main()
