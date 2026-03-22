# Advising_Bot
Chatbot that answers course advising questions for Stony Brook University students 

## Program Technicals 
- Used Python web scraper to scrape all data from Stony Brook's Undergraduate Bulletin website as data 
- Implemented RAG system with Pinecone database. Pinecone embeds all the data, then embeds the user query and returns the top-k results
- A LLM backbone takes in the information as context to generate response.  


## Current Problems to work on
- chatbot should answer more general, broader questions that requires thinking and not only search queries 
- Implement memory into the chatbot to enable ? 
- How to incorporate updated/newest information 
- Defend against jailbreaking 
    - against irrelevant queries 
    - against disguised irrelevant queries  
- more complete/better polished query responses 

## Queries it can't answer yet 
- "Give me all courses in CSE" 
- How many CSE classes are there? 
- What is the prereq to get into CS major? 
- I want to know what CSE 114 does. Before that, I need to know what O(n) means, help me with this