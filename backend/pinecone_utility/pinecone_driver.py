'''
this file contains all the pinecone utility functions 
'''
from dotenv import load_dotenv 
from pinecone import Pinecone 
import os 
import time
import pandas as pd 

load_dotenv() 
pinecone_key = os.getenv("PINECONE_KEY")  
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
        raise ValueError("Index_name not found at Pinecone")
 
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
def insert_pc_data(pc_index, records, namespace, batch_size=24, max_retries=5):
    ''' 
    @param pc_index: the pinecone index 
    @param records: the complete records to be inserted 
    '''
    if (not pc_index or not records or not namespace):
        raise ValueError("One of the parameters is NULL")
    assert batch_size<=96, "Batch size is max 96 to insert into Pinecone"
    
    for i in range(0, len(records), batch_size):
        batch_records = records[i:i+batch_size]
        retry_delay_seconds = 5
        for attempt in range(max_retries):
            try:
                pc_index.upsert_records(namespace=namespace, records=batch_records)
                break
            except Exception as e:
                err_text = str(e)
                is_rate_limited = "RESOURCE_EXHAUSTED" in err_text or "Too Many Requests" in err_text or "(429)" in err_text
                if is_rate_limited and attempt < max_retries - 1:
                    print(f"Rate limited on batch starting at {i}. Retrying in {retry_delay_seconds}s...")
                    time.sleep(retry_delay_seconds)
                    retry_delay_seconds = min(retry_delay_seconds * 2, 60)
                    continue
                raise RuntimeError(f"Failed at inserting records to Pinecone Index (batch start={i})") from e

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
    

def upsert_to_pinecone(csv_file, index_name, namespace):
    '''
    @param csv_file: the csv file to be inserted in pinecone
    @param index_name: the name of the index to be inserted into
    @param namespace: the namespace within the index to be inserted into inside Pinecone 
    '''
    df = pd.read_csv(csv_file)
    records = df.to_dict(orient='records')
    try:
        pc_index = create_pc_index(index_name)
        insert_pc_data(pc_index, records, namespace)
        print(f"Successfully upserted data from {csv_file} to Pinecone index '{index_name}' in namespace '{namespace}'.")
    except Exception as e:
        print(f"Error occurred while upserting data: {e}")
        raise
