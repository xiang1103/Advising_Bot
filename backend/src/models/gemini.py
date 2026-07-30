'''
Gemini API 
'''
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os 

load_dotenv()
gemini_key = os.getenv("GEMINI_KEY")

def create_model(gemini_model: str = "gemini-3-flash-preview"):
    model = ChatGoogleGenerativeAI(
        api_key=gemini_key,
        model=gemini_model,
        temperature=1.0,
        max_retries=2,
    )
    return model