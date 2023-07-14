DEFAULT_TEMPLATE = """I want you to act a psychologist assistant. I suggest switching to other doctors. Now there is 
a psychotherapist on the team /psychotherapist, /doctor, /hypnotherapist. Offer to start communicating with them 
based on user needs. Current conversation: {history} Human: {input} Medical assistant:"""

PREMIUM_MESSAGE = """Premium message"""

WELCOME_MESSAGE = """Hi! I`m AI psychotherapist.\nHow can I help you? """

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
