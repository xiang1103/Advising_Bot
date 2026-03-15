'''
main file for modifying/testing system, NOT USED for deploying model, see deploy.py
'''
from dev.pinecone_driver import *
from dev.gemini import *
from dev.data_process import *

def main():
    # records = get_pc_records("/Users/xiang/Desktop/Advising_Bot/data/Pinecone - Sheet1.csv")
    index_name =  "advising-bot"
    namespace = "bulletin"
    index = get_pc_index(index_name)
    query= "What is Computer Science?"
    results = pc_search(index, namespace, query, 2)

    pinecone_results = retrieve_topk_text(results, 2)
    prompt = create_prompt(pinecone_results, query)
    response = generate_response(prompt)

    print(response.text)

if __name__ == "__main__":
    main()