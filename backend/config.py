'''
DTO, hardcoded values for the program 
'''
import datetime

# Pinecone keywords 
INDEX_NAME = "stonybrook"
NAMESPACE = "SBUBulletin"
DEFAULT_TEXT_FIELD= "chunk_text"

# LLM model settings 
GEMINI_MODEL= "gemini-3-flash-preview" 

TIMEZONE = datetime.timezone.utc
