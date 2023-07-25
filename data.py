from pydantic import BaseModel

class Start(BaseModel):
    user_id: int

class Message(BaseModel):
    message: str
    user_id: int