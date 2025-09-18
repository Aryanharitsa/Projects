from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseProvider(ABC):
    """Base class for all LLM providers"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    @abstractmethod
    def get_models(self) -> List[str]:
        """Return list of available models for this provider"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> List[str]:
        """Return list of supported parameters for this provider"""
        pass
    
    @abstractmethod
    def build_request(self, session) -> Dict[str, Any]:
        """Build API request payload from session"""
        pass
    
    @abstractmethod
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse API response and return standardized format"""
        pass
    
    @abstractmethod
    def make_request(self, session) -> Dict[str, Any]:
        """Make API call and return response"""
        pass
    
    def supports_json_mode(self) -> bool:
        """Return True if provider supports JSON mode"""
        return False
    
    def supports_reasoning_effort(self) -> bool:
        """Return True if provider supports reasoning effort parameter"""
        return False
