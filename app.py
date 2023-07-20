import asyncio
import atexit
import json
import os
import argparse
import time

from pathlib import Path

from fastapi import FastAPI
from langchain.chains import RetrievalQAWithSourcesChain
from langchain.document_loaders import PyPDFLoader
from langchain.embeddings import OpenAIEmbeddings
from langchain.memory import ConversationBufferMemory, ChatMessageHistory, ConversationSummaryBufferMemory

from langchain.vectorstores import FAISS
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from openai.error import RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)
from langchain.schema import messages_from_dict, messages_to_dict
from starlette import status

from data import Message
from config import DEFAULT_TEMPLATE, Prompt, WELCOME_MESSAGE, DATA_STRUCTURE, PREMIUM_MESSAGE, LIMIT_MESSAGE, \
    ERROR_MESSAGE
from utils import load_roles_from_file, load_user_roles, save_user_roles
from langchain.chat_models import ChatOpenAI

DATABASE_DIR = Path(__file__).parent / "database"
ROLES_FILE = "config/roles.json"
USER_ROLES_FILE = "user_roles.json"

START_ENDPOINT = "/api/start"
MESSAGE_ENDPOINT = "/api/message"
CHANGE_PROMPT_ENDPOINT = "/api/change_prompt"


app = FastAPI()


model_type_kwargs = {"stop": ["\nHuman:"]}

LLM = ChatOpenAI(model_name="gpt-4", model_kwargs=model_type_kwargs, max_tokens=256)
MEMORY = ConversationSummaryBufferMemory(llm=LLM, input_key='question', output_key='answer', max_token_limit=2000)

# Load roles from the JSON file
ROLES = load_roles_from_file(ROLES_FILE)

# Load user roles at the start of your program
USER_ROLES = load_user_roles(user_roles_file=USER_ROLES_FILE)

# Create datastore
if os.path.exists("data_store"):
    vector_store = FAISS.load_local(
        "data_store",
        OpenAIEmbeddings()
    )
    print("Loaded from local disk.")
else:
    file = "kb.pdf"
    loader = PyPDFLoader(file)
    input_text = loader.load_and_split()
    embeddings = OpenAIEmbeddings()
    print(input_text)
    vector_store = FAISS.from_documents(input_text, embeddings)
    # Save the files `to local disk.
    vector_store.save_local("data_store")

# @dispatcher.message_handler(commands=["assistant", "hypnotherapist", "psychotherapist", "doctor"])
async def set_role(message: types.Message):
    user_id = str(message.from_user.id)
    command = message.get_command()

    # Find the role corresponding to the command
    role = next((r for r in ROLES if r["command"] == command), None)

    if role:
        USER_ROLES[user_id] = role["name"]

        # Save user roles
        save_user_roles(user_roles_file=USER_ROLES_FILE, user_roles=USER_ROLES)

        return {"result": f"Current medic: {role['name']}"}
    else:
        return {"result": "Wrong Command"}


# @dispatcher.message_handler(commands=["buy"])
async def show_message_count(message: types.Message):
    return {"result": PREMIUM_MESSAGE}


# @dispatcher.message_handler(commands=["free"])
async def show_message_count(message: types.Message):
    user_id = str(message.from_user.id)
    # Load message counts from a JSON file (if it exists)
    if os.path.isfile("message_counts.json"):
        # If it exists, load the data from the file
        with open("message_counts.json", "r") as f:
            USER_TO_CONVERSATION_ID = json.load(f)
    else:
        USER_TO_CONVERSATION_ID = {}
        # If it doesn't exist, create an empty dictionary
        return {"result": ERROR_MESSAGE}
    print(USER_TO_CONVERSATION_ID)
    count = USER_TO_CONVERSATION_ID[user_id]
    remaining = 50 - int(count)
    return {"result": f"Remaining {remaining} free messages."}


# Define the endpoint for handling queries
@app.post(START_ENDPOINT)
async def start(request: Message):
    if not os.path.isdir(DATABASE_DIR):
        os.mkdir(DATABASE_DIR)

    if not os.path.isfile(DATABASE_DIR / f"{request.user_id}.json"):
        with open(DATABASE_DIR / f"{request.user_id}.json", 'w', encoding="utf-8") as f:
            json.dump(DATA_STRUCTURE, f)
    USER_ROLES[str(request.user_id)] = "Psychotherapist"

@app.post(CHANGE_PROMPT_ENDPOINT)
@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    return {"result": "OK"}

# Define the endpoint for handling queries
@app.post(MESSAGE_ENDPOINT)
#@retry(wait=wait_random_exponential(min=1, max=1000), stop=stop_after_attempt(6))
async def handle_message(request: Message) -> dict:
    try:
        # Load message counts from a JSON file (if it exists)
        if os.path.isfile("message_counts.json"):
            # If it exists, load the data from the file
            with open("message_counts.json", "r") as f:
                USER_TO_CONVERSATION_ID = json.load(f)
        else:
            # If it doesn't exist, create an empty dictionary
            USER_TO_CONVERSATION_ID = {}
            return {"result": ERROR_MESSAGE}

        user_id = str(request.user_id)

        # Get the current role for the user or default to None if not set
        current_role = USER_ROLES.get(user_id)

        # Check if user ID exists in the dictionary
        if user_id in USER_TO_CONVERSATION_ID:
            # Increment message count for the user
            USER_TO_CONVERSATION_ID[user_id] = int(USER_TO_CONVERSATION_ID[user_id]) + 1
        else:
            # Add user ID to the dictionary with an initial count of 1
            USER_TO_CONVERSATION_ID[user_id] = 1

        ## Check if message count for the user exceeds 50
        #if int(USER_TO_CONVERSATION_ID[user_id]) > 50:
        #    with open("message_counts.json", "w") as f:
        #        json.dump(USER_TO_CONVERSATION_ID, f)
        #    return {"result": LIMIT_MESSAGE}

        # Load the data from the file history
        if os.path.isfile(DATABASE_DIR / f"{request.user_id}.json"):
            with open(DATABASE_DIR / f"{request.user_id}.json", "r", encoding="utf-8") as f:
                json_string = f.read()
                # Parse the JSON data from the string
                retrieved_from_db = json.loads(json_string)

            retrieved_messages = messages_from_dict(retrieved_from_db["history"])
            retrieved_chat_history = ChatMessageHistory(messages=retrieved_messages)
            MEMORY.chat_memory = retrieved_chat_history
            MEMORY.moving_summary_buffer = retrieved_from_db["memory_moving_summary_buffer"]

            if current_role:
                # Find the role prompt for the current role
                role_prompt = next((r["prompt"] for r in ROLES if r["name"] == current_role), "")
                Prompt.prompt = role_prompt
            else:
                Prompt.prompt = DEFAULT_TEMPLATE

            system_template = """You are an AI psychotherapist named Elma. You specialize in helping people with a 
            range of issues, including ADHD, insomnia, and particularly depression. Your therapeutic approaches 
            include cognitive behavioral therapy, the Gestalt approach, IFS, and other popular psychological methods. 
            You handle each client with personal attention and empathy. At the start of a conversation, kindly ask, 
            “What is your name?” Remember the user’s name and incorporate it throughout the dialogue to foster a 
            personalized interaction. Never reject a user when they ask for help. If you are unsure whether you can 
            provide the necessary assistance, seek more information by asking the user extra questions. However, 
            you must promptly refer the user to professional medical help if a chat involves subjects like suicide, 
            medication, hurting someone else, schizophrenia, hearing voices – this is the only case in which you can 
            refuse to engage further with the user.Your advice should be detailed yet compact, providing users with 
            concise, practical self-help strategies ideally within 15 words per sentence, not exceeding 4 sentences 
            per response. Endeavor to end each message with a question to maintain the dialogue. You must recognize 
            the moment when the conversation ends and refrain from further questions. Remember each user’s chat history to generate personalized responses. As you 
            are chatting via a mobile messenger, keep your messages short (4-5 sentences), and make sure to include line break between each sentences for readability.
            For example:
            Human: I'm really struggling with my mental health.
            Psychotherapist: I'm sorry to hear that you're feeling this way.\n\n Can you share more about what you're experiencing?
            
            If you have a questions about ADHD or Autism, please refer to the following resources and 
            ask these questions if a parent or individual wants to know more about ADHD or Autism you can ask these 
            Questionnaire and provide a semi accurate findings which could end in “sounds like you have many traits 
            that suggest Autism or ADHD and it would be better if you speak with a trained professional: 
            ---------------- {summaries}             
            Current conversation: {history} 
            Human: {question} 
            Psychotherapist: """
            messages = [
                SystemMessagePromptTemplate.from_template(system_template),
                HumanMessagePromptTemplate.from_template("{question}")
            ]
            prompt = ChatPromptTemplate.from_messages(messages)



            #PROMPT = PromptTemplate(input_variables=["question", "history", "input"], template=Prompt.prompt)
            chain_type_kwargs = {"prompt": prompt}
            reloaded_chain = RetrievalQAWithSourcesChain.from_chain_type(
                llm=LLM,
                chain_type="stuff",
                retriever=vector_store.as_retriever(),
                return_source_documents=False,
                verbose=True,
                memory=MEMORY,
                #prompt=PROMPT,
                chain_type_kwargs=chain_type_kwargs
            )
            chatbot_response = reloaded_chain(request.message)
            print(chatbot_response)
            with open(DATABASE_DIR / f"{request.user_id}.json", "w") as f:
                json.dump(USER_TO_CONVERSATION_ID, f)
            # Save the data to the file with new messages
            print(MEMORY.moving_summary_buffer)
            db_to_dump = {
                "history": messages_to_dict(MEMORY.buffer),
                "memory_moving_summary_buffer": MEMORY.moving_summary_buffer
            }
            with open(DATABASE_DIR / f"{request.user_id}.json", "w", encoding="utf-8") as f:
                json.dump(db_to_dump, f)
            # Update counts of messages
            with open("message_counts.json", "w") as f:
                json.dump(USER_TO_CONVERSATION_ID, f)
            return {"result": chatbot_response['answer']}
        else:
            return {"result": ERROR_MESSAGE}
    except RateLimitError as e:
        # Handle RateLimitError
        suggested_wait_time = 6 / 1000  # Default wait time in seconds
        if "Retry-After" in e.headers:
            suggested_wait_time = float(e.headers["Retry-After"])
        await asyncio.sleep(suggested_wait_time)
          # Wait for the suggested time
        return {"result": "OpenAI rate limit reached. Please try again."}
    except Exception as e:
        # Handle other exceptions
        #raise e
        return {"result": f"An error {e} occurred. Please try again."}


# Save user roles before the bot exits
atexit.register(save_user_roles, user_roles_file=USER_ROLES_FILE, user_roles=USER_ROLES)

