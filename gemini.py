from google import genai 
import os 
from dotenv import load_dotenv 
load_dotenv() 
gemini_key = os.getenv("Gemini_key")  


client = genai.Client(api_key=gemini_key) 

system_role= "You are a strict, factual AI assistant answering college students' answers. " \
            "Questions are answered using ONLY provided context. If the context does not contain the answer," \
            "you should answer: 'I do not have this information available'. " \
            "These context are provided to you right begore the user question under the <context> tags" 


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
