''' 
all functions regarding upsering, data processing with pinecone database  
'''
import pandas as pd 
import time 
from backend.clients.pinecone_driver import create_pc_index
import logging 

logger= logging.getLogger(__name__)
# read data to get records for pinecone 
def get_pc_records(path):
    '''
    @param path: path to the data 
    '''
    df = pd.read_csv(path)
    df['_id'] = df['_id'].astype(str) 
    records = df.to_dict("records")
    return records 

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