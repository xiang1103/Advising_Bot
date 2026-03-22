import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dev.pinecone_driver import insert_pc_data, create_pc_index
import pandas as pd

def upsert_to_pinecone(csv_file, index_name, namespace):
    '''
    @param csv_file: the csv file to be inserted in pinecone
    @param index_name: the name of the index to be inserted into
    @param namespace: the namespace within the index to be inserted into
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



if __name__ == "__main__":
    csv_file = "./data/stonybrook_pinecone_data.csv"
    index_name = "stonybrook"
    namespace = "SBUBulletin"
    upsert_to_pinecone(csv_file, index_name, namespace)