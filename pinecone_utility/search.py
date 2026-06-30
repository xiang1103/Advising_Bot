''' 
file for all functions related to searching/using Pinecone 
'''

from pinecone_utility.pinecone_driver import get_pc_index, pc_search, retrieve_topk_text
from dev.gemini import generate_response_stream 

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