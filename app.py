import base64
import json
import time
from pathlib import Path
import boto3
import aiohttp
from starlette.responses import PlainTextResponse
from PIL import Image
import io
from converbot.app.bot_utils import create_conversation
from converbot.app.data import CompanionList, SwitchCompanion, DeleteCompanion, DeleteAllCompanions, Debug, Message, \
    NewCompanion, NewUser, CompanionListOut, SelfieRequest, CompanionExists, DeleteHistoryCompanion, SelfieWebRequest, \
    SQLHistory, Tone, SQLHistoryCount, ToneWeb
from converbot.constants import PROD_ENV, DEV_ENV, CONVERSATION_SAVE_DIR, bot_descriptions, prompt_templs
from converbot.database.conversations import ConversationDB
from converbot.database.history_writer import SQLHistoryWriter
from converbot.handlers.selfie_prompt_handler import SelfieStyleHandler
from converbot.handlers.text_style_handler import ConversationTextStyleHandler
from converbot.prompt.generator import ConversationalPromptGenerator
from fastapi import FastAPI, Response, status, HTTPException
import os

from converbot.utils.utils import read_json_file

ENABLE_SLEEP = True
app = FastAPI()

os.environ['SQL_CONFIG_PATH'] = '../../configs/sql_config_prod.json'
os.environ['MODEL_CONFIG_PATH'] = '../../configs/model_config.json'
os.environ['PROMPT_CONFIG_PATH'] = '../../configs/prompt_config.json'
os.environ['ENVIRONMENT'] = 'dev'

HISTORY_WRITER = SQLHistoryWriter.from_config(Path(os.environ.get('SQL_CONFIG_PATH')))

CONVERSATIONS = ConversationDB()
CONVERSATIONS.load_conversations(connection=HISTORY_WRITER.connection)

PROMPT_GENERATOR = ConversationalPromptGenerator.from_json(
    Path(os.environ.get('PROMPT_CONFIG_PATH'))
)

COMPANION_LIST_ENDPOINT = "/api/list_companion"
SWITCH_COMPANION_ENDPOINT = "/api/switch_companion"
DELETE_COMPANION_ENDPOINT = "/api/delete_companion"
DELETE_ALL_COMPANIONS_ENDPOINT = "/api/delete_all_companions"
MESSAGE_ENDPOINT = "/api/message"
DEBUG_ENDPOINT = "/api/debug"
NEW_USER_ENDPOINT = "/api/new_user"
NEW_COMPANION_ENDPOINT = "/api/new_companion"
NEW_COMPANION_ENDPOINT_WEB = "/api/new_companion_web"
SLEEP_ENDPOINT = "/api/sleep"
SELFIE_ENDPOINT = "/api/selfie"
CONVERSATION_EXISTS_ENDPOINT = "/api/is_conversation_exists"
DELETE_CHAT_HISTORY_ENDPOINT = "/api/delete_history"
SELFIE_ENDPOINT_WEB = "/api/selfie_web"
SQL_CHAT_HISTORY_ENDPOINT_WEB = "/api/sql_history_web"
SQL_GET_CHAT_HISTORY_ENDPOINT_WEB = "/api/get_sql_history_web"
TONE_ENDPOINT_WEB = "/api/tone_web"
SQL_COUNT_CHAT_HISTORY_ENDPOINT_WEB = "/api/count_messages_sql_web"
SQL_COUNT_COMPANION_CHAT_HISTORY_ENDPOINT_WEB = "/api/count_companion_messages_sql_web"
TONE_COMP_ID_ENDPOINT_WEB = "/api/tone_companion_web"
SELFIE_HANDLER = SelfieStyleHandler()

S3 = boto3.client('s3',
                  region_name='us-east-1',
                  endpoint_url='https://47ec7d0d5b6a6c2bcda5211d2d412fd0.r2.cloudflarestorage.com',
                  aws_access_key_id='be539a4b5e965428c81a572b0f699a57',
                  aws_secret_access_key='d369f72be90a632aa57839af27e53fc6d77ce57e3e6cd07f64252c81e7805bf9'
                  )


@app.post(NEW_USER_ENDPOINT)
async def new_user(request: NewUser):
    user_id = request.user_id
    txt_style = ConversationTextStyleHandler()
    output_paths = []
    for description, template in zip(bot_descriptions, prompt_templs):
        time.sleep(1)
        conversation_id = f"{user_id}-{int(time.time())}"
        output_paths.append(conversation_id)
        HISTORY_WRITER.create_new_user(user_id, conversation_id, template, description)
    return output_paths


@app.post(DELETE_CHAT_HISTORY_ENDPOINT)
async def delete_chat_history(request: DeleteHistoryCompanion):
    deleted_conversation = CONVERSATIONS.delete_conversation_history(request.user_id, request.companion_id,
                                                                     connection=HISTORY_WRITER.connection)
    return PlainTextResponse(deleted_conversation)


@app.get(CONVERSATION_EXISTS_ENDPOINT)
async def is_conversation_exists(request: CompanionExists):
    conversation = CONVERSATIONS.get_conversation(request.user_id)
    exists = True
    if conversation is None:
        exists = False
    return {"exists": exists}


@app.post(SELFIE_ENDPOINT)
async def generate_selfie(request: SelfieRequest):
    endpoint_url = "https://api2.makeai.run/v1/api/infer/txt2img"
    headers = {"token": "5473e92142294dc88e0d39d6a7e40843"}
    conv_id = Path(CONVERSATIONS.get_conversation_id(request.user_id)).with_suffix('.json')
    path_to_json = CONVERSATION_SAVE_DIR / str(request.user_id) / conv_id
    bot_description = read_json_file(path_to_json)["bot_description"]
    prompt = SELFIE_HANDLER(bot_description)
    print(prompt)
    data = {
        "prompt": prompt,
        "negative_prompt": "worst quality, lowres, nude, nudity, breasts, nipples, hands, fingers",
        "model": "realisticVisionV20_v20.safetensors",
        "vae": "vae-ft-mse-840000-ema-pruned.ckpt",
        "steps": 35,
        "width": 512,
        "height": 512,
        "cfg": 7,
        "seed": -1,
        "scheduler": "Euler a",
        "mode": "json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint_url, headers=headers, json=data) as response:
            if response.status == 200:
                content = await response.json()
                return {"image": content["content"]["image"]}
            else:
                raise HTTPException(status_code=response.status, detail=response.reason)


@app.post(SELFIE_ENDPOINT_WEB)
async def generate_selfie_web(request: SelfieWebRequest):
    endpoint_url = "https://api2.makeai.run/v1/api/infer/txt2img"
    headers = {"token": "5473e92142294dc88e0d39d6a7e40843"}
    bot_description = HISTORY_WRITER.get_bot_description_of_companion_by_user_id(request.companion_id)
    prompt = SELFIE_HANDLER(bot_description)
    print(prompt)
    data = {
        "prompt": prompt,
        "negative_prompt": "worst quality, lowres, nude, nudity, breasts, nipples, hands, fingers",
        "model": "realisticVisionV20_v20.safetensors",
        "vae": "vae-ft-mse-840000-ema-pruned.ckpt",
        "steps": 35,
        "width": 512,
        "height": 512,
        "cfg": 7,
        "seed": -1,
        "scheduler": "Euler a",
        "mode": "json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint_url, headers=headers, json=data) as response:
            print(response.status)
            if response.status == 200:
                content = await response.json()
                # Decode the base64-encoded image data
                image_data = base64.b64decode(content["content"]["image"])

                # Convert the image data to a PIL Image object
                image = Image.open(io.BytesIO(image_data))

                # Save the image locally in JPG format with 85% compression
                local_path = f"{request.companion_id}.jpg"  # Replace with the desired local path
                image.save(local_path, "JPEG", quality=85)

                # Upload the image data to S3
                try:
                    # Specify the bucket and key where you want to store the image
                    bucket_name = 'neecebotprofile'
                    key_name = f'{request.companion_id}.jpg'
                    with open(local_path, 'rb') as file:
                        S3.put_object(Bucket=bucket_name, Key=key_name, Body=file, ACL='public-read')

                    # Delete the local file
                    os.remove(local_path)

                    # Generate the URL for the saved image
                    selfie_url = f"https://companions.makeaitemp.com/{request.companion_id}.jpg"
                    HISTORY_WRITER.set_selfie_url(request.companion_id, selfie_url)
                    return {"image": f'{request.companion_id}.jpg'}

                except Exception as e:
                    print(e)
            else:
                raise HTTPException(status_code=response.status, detail=response.reason)


@app.post(NEW_COMPANION_ENDPOINT)
async def new_companion(request: NewCompanion):
    user_id = request.user_id
    name = request.name
    age = request.age
    gender = request.gender
    interest = request.interest
    profession = request.profession
    appearance = request.appearance
    relationship = request.relationship
    mood = request.mood

    context = (
        f"Name: {name}\n"
        f"Age: {age}\n"
        f"Gender: {gender}\n"
        f"Interests: {interest}\n"
        f"Profession: {profession}\n"
        f"Appearance: {appearance}\n"
        f"Relationship status: {relationship}\n"
        f"Personality: {mood}\n"
    )
    intro = f"This is the role you will play in the conversation:\n\n"
    conversation = create_conversation(
        prompt=PROMPT_GENERATOR(intro + context),
        tone=mood,
        config_path=Path(os.environ.get('MODEL_CONFIG_PATH'))
    )
    CONVERSATIONS.add_conversation(user_id, conversation, context)
    CONVERSATIONS.serialize_user_conversation(user_id=request.user_id, connection=HISTORY_WRITER.connection)
    return PlainTextResponse(context)


@app.post(NEW_COMPANION_ENDPOINT_WEB)
async def new_companion(request: NewCompanion):
    user_id = request.user_id
    name = request.name
    age = request.age
    gender = request.gender
    interest = request.interest
    profession = request.profession
    appearance = request.appearance
    relationship = request.relationship
    mood = request.mood

    context = (
        f"Name: {name}\n"
        f"Age: {age}\n"
        f"Gender: {gender}\n"
        f"Interests: {interest}\n"
        f"Profession: {profession}\n"
        f"Appearance: {appearance}\n"
        f"Relationship status: {relationship}\n"
        f"Personality: {mood}\n"
    )
    intro = f"This is the role you will play in the conversation:\n\n"
    conversation = create_conversation(
        prompt=PROMPT_GENERATOR(intro + context),
        tone=mood,
        config_path=Path(os.environ.get('MODEL_CONFIG_PATH'))
    )
    CONVERSATIONS.add_conversation(user_id, conversation, context)
    CONVERSATIONS.serialize_user_conversation(user_id=request.user_id, connection=HISTORY_WRITER.connection)
    companion_id = CONVERSATIONS.get_conversation_id_by_user_id(request.user_id)
    return {"context": context,
            "companion_id": companion_id
            }


@app.post(SQL_CHAT_HISTORY_ENDPOINT_WEB)
async def get_sql_messages(request: SQLHistory):
    try:
        messages = HISTORY_WRITER.get_chat_history(conversation_id=request.companion_id, user_id=request.user_id)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(SQL_COUNT_CHAT_HISTORY_ENDPOINT_WEB)
async def get_count_sql_messages_by_user_id(request: SQLHistoryCount):
    try:
        messages_count = HISTORY_WRITER.get_message_count_by_user_id(user_id=request.user_id)
        return messages_count
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(SQL_COUNT_COMPANION_CHAT_HISTORY_ENDPOINT_WEB)
async def get_count_sql_messages_by_user_id_and_companion_id(request: SQLHistory):
    try:
        messages_count = HISTORY_WRITER.get_message_count_by_user_and_conversation_id(user_id=request.user_id,
                                                                                      conversation_id=request.companion_id, )
        return messages_count
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(SQL_GET_CHAT_HISTORY_ENDPOINT_WEB)
async def get_all_sql_messages():
    try:
        messages = HISTORY_WRITER.get_all_messages()
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(COMPANION_LIST_ENDPOINT)
async def companions_list(request: CompanionList):
    bot_descriptions = CONVERSATIONS.get_companion_descriptions_list(request.user_id,
                                                                     connection=HISTORY_WRITER.connection)

    if bot_descriptions is None:
        return None

    companion_list = []
    for bot_description, conv_id, image_path_s3 in bot_descriptions:
        companion_list.append(CompanionListOut(description=bot_description,
                                               companion_id=conv_id,
                                               image_path_on_s3=image_path_s3
                                               )
                              )
    return companion_list


@app.post(SWITCH_COMPANION_ENDPOINT)
async def load_conversation(request: SwitchCompanion):
    loaded_conversation, bot_description = CONVERSATIONS.load_conversation(request.user_id, request.companion_id,
                                                                           connection=HISTORY_WRITER.connection)
    if bot_description is not None:
        return bot_description
    return None


@app.post(DELETE_COMPANION_ENDPOINT)
async def delete_conversation(request: DeleteCompanion):
    deleted_conversation = CONVERSATIONS.delete_conversation(request.user_id, request.companion_id,
                                                             connection=HISTORY_WRITER.connection)

    return PlainTextResponse(deleted_conversation)


@app.post(DELETE_ALL_COMPANIONS_ENDPOINT)
async def delete_all_conversations(request: DeleteAllCompanions):
    deleted_all_conversations = CONVERSATIONS.delete_all_conversations_by_user_id(request.user_id,
                                                                                  connection=HISTORY_WRITER.connection)

    return PlainTextResponse(deleted_all_conversations)


@app.post(DEBUG_ENDPOINT)
async def debug(request: Debug):
    conversation = CONVERSATIONS.get_conversation(request.user_id)
    if conversation is None:
        return Response(status_code=status.HTTP_406_NOT_ACCEPTABLE)
    state = conversation.change_debug_mode()
    if state:

        text = "В«Debug mode onВ»\nPlease continue the discussion with your companion"

    else:
        text = "В«Debug mode offВ»\nPlease continue the discussion with your companion"

    return PlainTextResponse(text)


@app.post(TONE_ENDPOINT_WEB)
async def handle_tone(request: Tone):
    # if request.content.startswith("/tone"):
    #    tone = request.content[6:]
    tone = request.content
    conversation = CONVERSATIONS.get_conversation(request.user_id)
    tone_info = f"Information В«{tone}В» has been added."
    conversation.set_tone(tone)
    CONVERSATIONS.serialize_user_conversation(user_id=request.user_id, connection=HISTORY_WRITER.connection)
    return PlainTextResponse(tone_info)


@app.post(TONE_COMP_ID_ENDPOINT_WEB)
async def handle_tone(request: ToneWeb):
    tone = request.content
    conversation = CONVERSATIONS.tone_for_conversation(request.user_id, request.companion_id,
                                                       connection=HISTORY_WRITER.connection)
    tone_info = f"Information В«{tone}В» has been added."
    conversation.set_tone(tone)
    CONVERSATIONS.serialize_user_conversation(user_id=request.user_id, connection=HISTORY_WRITER.connection)
    return PlainTextResponse(tone_info)


@app.post(MESSAGE_ENDPOINT)
async def handle_message(request: Message):
    # Agent side:
    if request.content.startswith("/tone"):
        tone = request.content[6:]
        conversation = CONVERSATIONS.get_conversation(request.user_id)
        tone_info = f"Information В«{tone}В» has been added."
        conversation.set_tone(tone)

        return PlainTextResponse(tone_info)

    conversation = CONVERSATIONS.get_conversation(request.user_id)
    if conversation is None:
        return Response(status_code=status.HTTP_406_NOT_ACCEPTABLE)
    chatbot_response = conversation.ask(request.content)
    chatbot_response = chatbot_response.replace('\n', '').replace('\r', '')
    HISTORY_WRITER.write_message(
        user_id=request.user_id,
        conversation_id=CONVERSATIONS.get_conversation_id(request.user_id),
        user_message=request.content,
        chatbot_message=chatbot_response,
        env=os.environ.get('ENVIRONMENT'),
    )
    CONVERSATIONS.serialize_user_conversation(user_id=request.user_id, connection=HISTORY_WRITER.connection)
    return PlainTextResponse(chatbot_response)
