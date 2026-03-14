from dotenv import load_dotenv 
from pinecone import Pinecone 
import os 

load_dotenv() 
pinecone_key = os.getenv("Pinecone_key")  

pc = Pinecone(api_key=pinecone_key)  
default_text_field= "chunk_text"

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
        raise (ValueError, "Index_name not found at Pinecone")
 
def create_pc_index(index_name, model="llama-text-embed-v2"):
    ''' 
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
                "field_map":{"text": default_text_field}
            }
        )
    else: 
        print("Index already Exists")
    return pc.Index(index_name)

# insert data into pinecone index's namespace 
def insert_pc_data(pc_index, records, namespace, batch_size=96):
    ''' 
    @param pc_index: the pinecone index 
    @param records: the complete records to be inserted 
    '''
    if (not pc_index or not records or not namespace):
        raise ValueError("One of the parameters is NULL")
    
    assert batch_size<=96, "Batch size is max 96 to insert into Pinecone"
    for i in range(len(records), batch_size):
        try: 
            pc_index.upsert_records(records[i:i+batch_size])
        except: 
            raise(RuntimeError, "Failed at inserting records to Pinecone Index") 


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
    except: 
        raise(RuntimeError, "Failed to find top_k responses from pinecone")
    