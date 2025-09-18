from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"

@dataclass
class Message:
    role: MessageRole
    content: str
    enabled: bool = True
    id: Optional[str] = None

@dataclass
class PromptSession:
    provider: str
    model: str
    params: Dict[str, Any] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)
    system_prompt: str = ""
    pkey: str = ""
    pvariables: Dict[str, str] = field(default_factory=dict)
    json_mode: bool = False
    mode: str = "universal"  # "universal" or "august"

