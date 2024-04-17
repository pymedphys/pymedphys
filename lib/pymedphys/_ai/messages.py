from typing import Literal, TypedDict

from anthropic import AI_PROMPT, HUMAN_PROMPT

Role = Literal["user", "assistant"]

USER: Role = "user"
ASSISTANT: Role = "assistant"

PromptMap: dict[Role, str] = {USER: HUMAN_PROMPT, ASSISTANT: AI_PROMPT}


class Message(TypedDict):
    role: Role
    content: str


Messages = list[Message]
