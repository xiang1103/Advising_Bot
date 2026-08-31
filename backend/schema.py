'''
utility models and functions that can be used 
'''
from pydantic import BaseModel
from uuid import UUID

# Pydantic classes for chat entities
class ChatRequest(BaseModel):
    thread_id: UUID     # convert str into valid UUID 
    thread_title: str
    message: str

class ThreadSummary(BaseModel): 
    id: UUID
    title: str 