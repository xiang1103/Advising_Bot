''' 
all functions regarding data processing 
'''
import pandas as pd 

# read data to get records for pinecone 
def get_pc_records(path):
    '''
    @param path: path to the data 
    '''
    df = pd.read_csv("/Users/xiang/Desktop/Advising_Bot/data/Pinecone - Sheet1.csv")
    df['_id'] = df['_id'].astype(str) 
    records = df.to_dict("records")
    return records 