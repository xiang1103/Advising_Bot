'''
DTO, hardcoded values for the program
'''
import datetime
from typing import Final 

# Pinecone keywords
INDEX_NAME = "stonybrook"
NAMESPACE = "SBUBulletin"
DEFAULT_TEXT_FIELD= "chunk_text"

# all supported models 
SELECTABLE_MODELS = {
    "gemini": "gemini",
    "qwen": "ollama",
}

# LLM model settings
GEMINI_MODEL= "gemini-3-flash-preview"
OLLAMA_DEFAULT_MODEL="qwen3:4b"
OLLAMA_SMALL_MODEL= "qwen3:1.7b"
OLLAMA_LARGE_MODEL= "qwen3:8b"

TIMEZONE = datetime.timezone.utc
