'''
LLM provider factory - constructs the chat model used by the LangGraph workflow
'''
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
gemini_key = os.getenv("Gemini_key")

def create_model(gemini_model: str = "gemini-3-flash-preview"):
    model = ChatGoogleGenerativeAI(
        api_key=gemini_key,
        model=gemini_model,
        temperature=1.0,
        max_retries=2,
    )
    return model