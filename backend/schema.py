'''
utility models and functions that can be used 
'''
from pydantic import BaseModel

# Pydantic classes for chat entities
class ChatRequest(BaseModel):
    thread_id: str
    message: str