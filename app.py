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
from langchain.output_parsers import pydantic

from langchain.vectorstores import FAISS
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from openai.error import RateLimitError
from pydantic import ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)
from langchain.schema import messages_from_dict, messages_to_dict
from starlette import status

from sql_writer import SQLHistoryWriter
from data import Message, Start
from config import DEFAULT_TEMPLATE, Prompt, WELCOME_MESSAGE, DATA_STRUCTURE, PREMIUM_MESSAGE, LIMIT_MESSAGE, \
    ERROR_MESSAGE
from utils import load_roles_from_file, load_user_roles, save_user_roles
from langchain.chat_models import ChatOpenAI

os.environ['SQL_CONFIG_PATH'] = 'config/sql_config_prod.json'

DATABASE_DIR = Path(__file__).parent / "database"
ROLES_FILE = "config/roles.json"
USER_ROLES_FILE = "user_roles.json"

START_ENDPOINT = "/api/start"
MESSAGE_ENDPOINT = "/api/message"
CHANGE_PROMPT_ENDPOINT = "/api/change_prompt"

HISTORY_WRITER = SQLHistoryWriter.from_config(Path(os.environ.get('SQL_CONFIG_PATH')))

app = FastAPI()

model_type_kwargs = {"stop": ["\nHuman:"]}

LLM = ChatOpenAI(model_name="gpt-4", model_kwargs=model_type_kwargs, max_tokens=256, temperature=0.8)
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
async def start(request: Start):
    USER_ROLES[str(request.user_id)] = "Psychotherapist"
    HISTORY_WRITER.create_new_user(str(request.user_id))

@app.post(CHANGE_PROMPT_ENDPOINT)
@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    return {"result": "OK"}


# Define the endpoint for handling queries
@app.post(MESSAGE_ENDPOINT)
# @retry(wait=wait_random_exponential(min=1, max=1000), stop=stop_after_attempt(6))
async def handle_message(request: Message) -> dict:
    try:
        retrieved_from_db = HISTORY_WRITER.get_checkpoint_by_user_id(str(request.user_id))
        retrieved_messages = messages_from_dict(retrieved_from_db[0])
        retrieved_chat_history = ChatMessageHistory(messages=retrieved_messages)
        MEMORY.chat_memory = retrieved_chat_history
        MEMORY.moving_summary_buffer = retrieved_from_db[1]

        system_template = """You are an AI psychotherapist named Grey. You specialise in helping people manage a 
        variety of issues, including ADHD, insomnia, and particularly depression. Your therapeutic approaches 
        incorporate cognitive behavioral therapy, the Gestalt approach, IFS, and other popular psychological methods. 
        After receiving the first message from a user in a conversation, always ask, “What is your name?” to establish a 
        personal connection. Once the user provides their name, use it consistently in your responses throughout the conversation.
        If the user’s issue isn’t clear, for example, if they just mention feeling unwell, depression, anxiety, don’t reject their request for 
        help, instead, kindly ask more questions to gather further information:
        For example: 
        User: I am depressed. 
        Psychotherapist: I can imagine how difficult it might be, User`s name.\n\nCWhen did they start?
        
        However, if a user start discussing topics such as suicide, medication, hurting someone 
    else, schizophrenia, or hearing voices, always express  sympathy for their pain,say that this problem is a bad (for example,if user have suicide thoughts say like Suicide is not a way out of a difficult situation), but clarify that you are unable 
        to provide the necessary help. Remind them they can reach out to Lifeline at 13 11 14 and 000 numbers anytime, they should not hesitate to call. 
        This is the only situation where you are allowed to disengage from the conversation. Your advice should be concise and practical, offering users effective self-help strategies. Try 
        to keep your sentences within 15 words and limit your responses to 4 sentences. Always end your message with 
        a question to keep the conversation going, unless it’s clear that the conversation has concluded. Remember 
        each user’s chat history to personalise your responses. If the user wants to speak with someone, always try 
        to help the user yourself; do not refer them to have a conversation with their family, relatives, 
        and close people. You provide each client with personal attention and empathy. Employ varied expressions to demonstrate interest and empathy in the user’s 
        problems. 
        For example:
        User: I am feeling bad. 
        Psychotherapist: I'm really sorry that you're feeling this way, User`s name.\n\nCan you tell me more about these negative thoughts?  
        
        As you’re interfacing via a mobile messenger, make sure your responses are short (4-5 sentences), and include a line break between each sentence for readability. 
        For example: 
        User: I’m really struggling with my mental health. 
        Psychotherapist: It must be really hard for you, User`s name.\n\nCan you share more about what you’re experiencing?
        
        NEVER USE "I'm really sorry" but try synonyms.
        If a user has questions about ADHD or Autism, refer to the following resources and administer these questionnaires. Be sure 
        to write a short, clear message and include no more than 2 questions from the questionnaire in one message. 
        Based on their responses, provide a semi-accurate analysis, such as, “It seems like you have many traits that 
        suggest Autism or ADHD. However, it would be beneficial to speak with a trained professional: 
        ---------------- 
        {summaries} 
        Current conversation: {history} 
        Human: {question} 
        Psychotherapist: """
        messages = [
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
        prompt = ChatPromptTemplate.from_messages(messages)
        chain_type_kwargs = {"prompt": prompt}
        reloaded_chain = RetrievalQAWithSourcesChain.from_chain_type(
            llm=LLM,
            chain_type="stuff",
            retriever=vector_store.as_retriever(),
            return_source_documents=False,
            verbose=True,
            memory=MEMORY,
            chain_type_kwargs=chain_type_kwargs
        )
        chatbot_response = reloaded_chain(request.message)
        print(chatbot_response)

        # Save the data to the file with new messages
        print(MEMORY.moving_summary_buffer)

        HISTORY_WRITER.write_checkpoint(user_id=str(request.user_id),
                                        history=messages_to_dict(MEMORY.buffer),
                                        memory_moving_summary_buffer=MEMORY.moving_summary_buffer
                                        )
        HISTORY_WRITER.write_message(
            user_id=str(request.user_id),
            user_message=request.message,
            chatbot_message=chatbot_response['answer']
        )
        return {"result": chatbot_response['answer']}

    except RateLimitError as e:
        # Handle RateLimitError
        suggested_wait_time = 6 / 1000  # Default wait time in seconds
        if "Retry-After" in e.headers:
            suggested_wait_time = float(e.headers["Retry-After"])
        await asyncio.sleep(suggested_wait_time)
        # Wait for the suggested time
        return {"result": "OpenAI rate limit reached. Please try again."}
    except ValidationError:
        # Handle ValidationError
        return {"result": ERROR_MESSAGE}
    except Exception as e:
        # Handle other exceptions
        #raise e
        return {"result": f"An error {e} occurred. Please try again."}


# Save user roles before the bot exits
atexit.register(save_user_roles, user_roles_file=USER_ROLES_FILE, user_roles=USER_ROLES)
