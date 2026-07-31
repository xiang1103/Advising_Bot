'''
this file contains all the pinecone utility functions 
'''
from dotenv import load_dotenv 
from pinecone import Pinecone 
import os 
from backend.config import DEFAULT_TEXT_FIELD 

load_dotenv() 
pinecone_key = os.getenv("PINECONE_KEY")  
pc = Pinecone(api_key=pinecone_key)  

# retrieve top k results from pinecone output to create context 
def retrieve_topk_text(results, top_k=3): 
    '''
    return array of top_k texts 
    ''' 
    if (not results): 
        raise ValueError("Input Array is None")
    
    result_arr= results['result']['hits']
    if (top_k>len(result_arr)):
        top_k = len(result_arr)

    return [hit["fields"]["chunk_text"].replace('\xad', '') for hit in (result_arr[:top_k])] 

# create index 
def get_pc_index(index_name): 
    ''' 
    @param index_name 
    retrieve pinecone index 
    '''
    if pc.has_index(index_name): 
        return pc.Index(index_name)
    else: 
        raise ValueError("Index_name not found at Pinecone")

def create_pc_index(index_name, model="llama-text-embed-v2"):
    ''' 
    Temperarily put here to avoid creating Pinecone() object twice 
    @param index_name: index name of the pinecone 
    @param model: pinecone model 
    '''
    if not pc.has_index(index_name): 
        pc.create_index_for_model(
            name=index_name,
            cloud="aws",
            region="us-east-1",
            embed={
                "model":model,
                "field_map":{"text": DEFAULT_TEXT_FIELD}
            }
        )
    else: 
        print("Index already Exists")
    return pc.Index(index_name)

# search for top_k results from pinecone 
def pc_search(index, namespace, query, top_k=5):
    ''' 
    @param index: pinecone index 
    @param namespace: the namespace within the index to get data 
    @param query: string of user question 
    @param top_k: number of answers from pinecone (top k number)
    '''
    if (not index or not namespace or not query):
        raise ValueError("One of the input parameters is NULL")
    assert top_k>=0, "Top_k must be above 0"
    try: 
        results = index.search(
        namespace=namespace,
        query={
            "top_k": top_k,
            "inputs": {
                'text': query
            }
        }
    )
        return results 
    except Exception as e: 
        raise RuntimeError("Failed to find top_k responses from pinecone") from e
    


