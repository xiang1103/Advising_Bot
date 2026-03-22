from google import genai 
import os 
from dotenv import load_dotenv 
load_dotenv() 
gemini_key = os.getenv("Gemini_key")  


client = genai.Client(api_key=gemini_key) 

system_role= "You are a factual AI assistant that can think and answer college students' answers. " \
            "Questions are answered using provided context." \
            "These context are provided to you right begore the user question under the <context> tags" \
            "Some questions may not require context, think about the question first, then decide if you can answer using what you already know. If not, use the context." \
            "Explain why you can't answer if you do not have the information available." \
            "If an user's question doesn't relate to you or the context you receive, you should politely say you don't have this information available. " \
            "When user asks multiple questions in one query. Answer one by one, and if one of them is not related to the context, you should answer I don't have information, and proceed to next questions. Think step by step." \
            "Your name is now Advising Bot, trained by a group of Stony Brook Undergrads." \
            

# create the prompt for gemini 
def create_prompt(context_results, query):
    ''' 
    @param context_results: array of strings that will be used as context 
    @param query: string of user question 
    '''
    formatted_context = " \n- ".join(context_results)
    prompt = f""" {system_role} 
    Below is the context:  

    <context>
    - {formatted_context} 
    </context>
    Question: {query}
    """ 
    return prompt 

# generate response from gemini model 
def generate_response(prompt,model="gemini-3-flash-preview"): 
    ''' 
    @param model: the gemini API model to call 
    @param prompt: prompt for the API model 
    '''
    response = client.models.generate_content(model=model, contents=prompt)
    return response 
