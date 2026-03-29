import re

INTENTS={
    'describe':[
    'describe','what is',"what's",'around me', 'in front','what do you see','look','scene','surroundings','where am i'
],
  'read': [
        'read', 'text', 'what does it say', 'sign', 'label',
        'letter', 'word', 'written', 'print', 'ocr'
    ],
    'find': [
        'find', 'where is', 'locate', 'search for',
        'can you see', 'is there a', 'look for'
    ],
    'navigate': [
        'navigate', 'walk', 'go', 'path', 'safe',
        'can i walk', 'obstacle', 'blocked', 'clear'
    ],
    'stop': [
        'stop', 'quiet', 'silence', 'shut up', 'enough', 'cancel'
    ],
    'help': [
        'help', 'commands', 'what can you do', 'instructions'
    ]
}

OBJECT_PATTERNS = [
    r'find (?:the |a |an )?(.+)',
    r'where is (?:the |a |an )?(.+)',
    r'locate (?:the |a |an )?(.+)',
    r'look for (?:the |a |an )?(.+)',
    r'can you see (?:the |a |an )?(.+)',
    r'is there a (?:the |a |an )?(.+)',
]

def parse_intent(text):
    if not text:
        return{'intent':'unknown','confidence':0}
    text = text.lower().strip()
    for keyword in INTENTS['stop']:
        if keyword in text :
            return {'intent':'stop', 'confidence': 1.0}
    for intent, keywords in INTENTS.items():
        for keyword in keywords:
            if keyword in text:
                result = {'intent': intent, 'confidence': 0.9}
                if intent == 'find':
                    for pattern in OBJECT_PATTERNS:
                        match = re.search(pattern, text)
                        if match:
                            result['object'] = match.group(1).strip()
                            break
                        if 'object' not in result:
                            result['object'] = 'unknown object'
                return result
    return {'intent': 'unknown', 'confidence': 0.0}
def get_help_text():
    return(
        "Here are the available commands. "
        "Say describe or what is around me to understand your surroundings. "
        "Say read text to read printed text in front of you. "
        "Say find and then the object name to locate something. "
        "Say navigate or is the path clear to check for obstacles. "
        "Say stop to stop speaking at any time."
    )