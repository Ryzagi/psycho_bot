from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import WELCOME_MESSAGE
import argparse
import asyncio

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types import KeyboardButton
import numpy as np
import os
import aiohttp
import requests
import asyncio
from datetime import datetime, timedelta

# Define a constant for the time window (in seconds)
MESSAGE_BUFFER_TIME_WINDOW = 3

# Define a dictionary to store user message buffers
user_message_buffers = {}

MAX_MESSAGE_LENGTH = 4000


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--telegram_token", help="Telegram bot token", type=str, required=True
    )
    return parser.parse_args()


args = parse_args()
# Set up the Telegram bot
bot = Bot(token=args.telegram_token)
storage = MemoryStorage()
dispatcher = Dispatcher(bot, storage=storage, loop=asyncio.get_event_loop())

# Define a ReplyKeyboardMarkup to show a "start" button
RESTART_KEYBOARD = types.ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton('/start')]], resize_keyboard=True, one_time_keyboard=True
)


def try_(func):
    async def try_except(message):
        error = ""
        for i in range(4):
            try:
                await func(message)
                return None
            except Exception as e:
                print(e)
                error = str(e).lower()
                pass
            await asyncio.sleep(1)
        if "overloaded with other requests" in error:
            await bot.send_message(
                message.from_user.id,
                "\nPlease, try again later, We are currently under heavy load",
            )
        else:
            await bot.send_message(
                message.from_user.id,
                '\nSomething went wrong, please type "/start" to start over',
            )
        return None

    return try_except


# Define a handler for the "/start" command
@dispatcher.message_handler(commands=["start"])
async def start(message: types.Message):
    # Show a "typing" action to the user
    await bot.send_chat_action(message.from_user.id, action=types.ChatActions.TYPING)

    async with aiohttp.ClientSession() as session:
        # Example for MESSAGE_ENDPOINT
        async with session.post(
                "http://localhost:8000/api/start",
                json={"message": message.text, "user_id": message.from_user.id},
        ) as response:
            result_text = await response.json()

    # Send a welcome message with a "start" button
    await bot.send_message(
        message.from_user.id,
        text=WELCOME_MESSAGE,
        # reply_markup=RESTART_KEYBOARD
    )


@dispatcher.message_handler()
async def handle_query_command(message: types.Message):
    user_id = message.from_user.id

    # Get the current timestamp
    now = datetime.now()

    # Check if the user already has a message buffer
    if user_id in user_message_buffers:
        # Get the previous message buffer for this user
        buffer_data = user_message_buffers[user_id]

        # Reset the timer for the task (cancel and create a new one)
        buffer_data["task"].cancel()
        buffer_data["task"] = asyncio.create_task(process_message_buffer(user_id))

        # Add the current message to the buffer
        buffer_data["messages"].append(message.text)
        buffer_data["timestamp"] = now
    else:
        # Create a new message buffer for the user
        user_message_buffers[user_id] = {
            "messages": [message.text],
            "timestamp": now,
            "task": asyncio.create_task(process_message_buffer(user_id))
        }

    await bot.send_chat_action(user_id, action=types.ChatActions.TYPING)


# Function to process the message buffer and send the API request
async def process_message_buffer(user_id):
    # Get the message buffer for the user
    buffer_data = user_message_buffers[user_id]

    # Get the current timestamp
    now = datetime.now()

    # Check if the time window has elapsed since the last message in the buffer
    if now - buffer_data["timestamp"] > timedelta(seconds=MESSAGE_BUFFER_TIME_WINDOW):
        # Combine the messages into a single request
        combined_message = "\n".join(buffer_data["messages"])

        # Send a request to the FastAPI endpoint to get the most relevant paragraph
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8000/api/message",
                json={"message": combined_message, "user_id": user_id},
            ) as response:
                result_text = await response.json()

        # Send the API response as separate messages to the user
        num_messages = len(result_text["result"]) // MAX_MESSAGE_LENGTH
        for i in range(num_messages + 1):
            await bot.send_chat_action(user_id, action=types.ChatActions.TYPING)
            await asyncio.sleep(1)
            await bot.send_message(
                user_id,
                text=result_text["result"][i * MAX_MESSAGE_LENGTH: (i + 1) * MAX_MESSAGE_LENGTH],
            )

        # Clear the user's message buffer after processing
        del user_message_buffers[user_id]
    else:
        # If the time window hasn't elapsed, create a new task to wait for the remaining time
        buffer_data["task"] = asyncio.create_task(wait_for_time_window(user_id))


# Function to wait for the time window before processing the buffer
async def wait_for_time_window(user_id):
    await asyncio.sleep(MESSAGE_BUFFER_TIME_WINDOW)
    # Process the message buffer after the time window
    await process_message_buffer(user_id)



# Define the handler function for the /query command
#dispatcher.message_handler()
#sync def handle_query_command(message: types.Message):
#   await bot.send_chat_action(
#       message.from_user.id, action=types.ChatActions.TYPING
#   )
#   # Send a request to the FastAPI endpoint to get the most relevant paragraph
#   async with aiohttp.ClientSession() as session:
#       # Example for MESSAGE_ENDPOINT
#       async with session.post(
#               "http://localhost:8000/api/message",
#               json={"message": message.text, "user_id": message.from_user.id},
#       ) as response:
#           result_text = await response.json()
#   print(result_text)
#   num_messages = len(result_text["result"]) // MAX_MESSAGE_LENGTH
#   await bot.send_chat_action(
#       message.from_user.id, action=types.ChatActions.TYPING
#   )
#   for i in range(num_messages + 1):
#       await bot.send_chat_action(
#           message.from_user.id, action=types.ChatActions.TYPING
#       )
#       await asyncio.sleep(1)
#       await bot.send_message(
#           message.from_user.id,
#           text=result_text["result"][i * MAX_MESSAGE_LENGTH: (i + 1) * MAX_MESSAGE_LENGTH],
#       )


# Start polling for updates from Telegram
if __name__ == "__main__":
    executor.start_polling(dispatcher, skip_updates=False)
