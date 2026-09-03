'''
LLM provider factory. Currently either gemini or qwen

'''
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel
from dotenv import load_dotenv
from backend.config import GEMINI_MODEL, OLLAMA_MODEL

import os

load_dotenv()
gemini_key = os.getenv("GEMINI_KEY")

def create_model(
    provider: str | None = None,
    model_name: str | None = None,
) -> BaseChatModel:
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            api_key=gemini_key,
            model=model_name or GEMINI_MODEL,
            temperature=1.0,
            max_retries=2,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model= OLLAMA_MODEL,
            temperature=1.0,
            reasoning=False,
        )

    raise ValueError("Unknown LLM provider")