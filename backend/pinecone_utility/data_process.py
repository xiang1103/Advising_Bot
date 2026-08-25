''' 
all functions regarding data processing into pinecone database  
'''
import pandas as pd 

# read data to get records for pinecone 
def get_pc_records(path):
    '''
    @param path: path to the data 
    '''
    df = pd.read_csv(path)
    df['_id'] = df['_id'].astype(str) 
    records = df.to_dict("records")
    return records 