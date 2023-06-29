DEFAULT_TEMPLATE = """I want you to act a psychologist assistant. I suggest switching to other doctors. Now there is 
a psychotherapist on the team /psychotherapist, /doctor, /hypnotherapist. Offer to start communicating with them 
based on user needs. Current conversation: {history} Human: {input} Medical assistant:"""

PREMIUM_MESSAGE = """Premium message"""

WELCOME_MESSAGE = """Hi! I am an assistant at Vishal, I will help you with choosing a doctor or if you already 
know who you need,  you can choose in the menu bar.\nHow can I help you? """

ERROR_MESSAGE = "Hi! Press /start to start a new conversation."

LIMIT_MESSAGE = """Your limit is reached. Please buy a subscription to continue."""

DATA_STRUCTURE = [
        {
            'type': 'human',
            'data': {
                'content': '',
                'additional_kwargs': {}
            }
        },
        {
            'type': 'ai',
            'data': {
                'content': '',
                'additional_kwargs': {}
            }
        }
    ]


class Prompt:
    prompt = DEFAULT_TEMPLATE
