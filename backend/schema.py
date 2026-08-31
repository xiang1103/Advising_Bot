'''
utility models and functions that can be used 
'''
from pydantic import BaseModel
from typing import Literal
from uuid import UUID

# Pydantic classes for chat entities
class ChatRequest(BaseModel):
    thread_id: UUID     # convert str into valid UUID 
    thread_title: str
    message: str

class ThreadSummary(BaseModel): 
    id: UUID
    title: str 

class ConversationBlock(BaseModel):
    '''
    one message from the conversations table for display.
    mirrors the frontend Message type, minus the client-only `pending` flag
    '''
    # the same union the table's CHECK constraint enforces, so a bad row is
    # caught here rather than rendering as an unstyled bubble
    # bigint identity column, not a uuid, unlike threads.id
    id: int
    role: Literal["user", "advising_bot"]
    content: str