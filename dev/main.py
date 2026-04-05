'''
main file for modifying/testing system, NOT USED for deploying model, see deploy.py
'''
from dev.pinecone_driver import *
from dev.gemini import *
from dev.data_process import *

def main():
    index_name =  "stonybrook"
    namespace = "SBUBulletin"
    index = get_pc_index(index_name)
    query= "How many credits is CSE 114?"
    results = pc_search(index, namespace, query, 2)

    pinecone_results = retrieve_topk_text(results, 2)
    model = create_model()
    advising_app = build_advising_graph(model=model, max_messages=8)
    response = generate_response(
        app=advising_app,
        query=query,
        context_results=pinecone_results,
        thread_id="dev-main-session",
    )

    print(response["messages"][-1].content)

if __name__ == "__main__":
    main()