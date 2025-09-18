import requests
import json
from typing import Dict, Any, List
from src.providers.base_provider import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider implementation"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.base_url = "https://api.anthropic.com/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
    
    def get_models(self) -> List[str]:
        """Return list of available Anthropic models"""
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]
    
    def get_parameters(self) -> List[str]:
        """Return list of supported parameters"""
        return ["temperature", "top_p", "max_tokens"]
    
    def supports_json_mode(self) -> bool:
        """Anthropic doesn't have explicit JSON mode"""
        return False
    
    def supports_reasoning_effort(self) -> bool:
        """Anthropic doesn't support reasoning effort"""
        return False
    
    def build_request(self, session) -> Dict[str, Any]:
        """Build Anthropic API request payload"""
        # Convert messages to Anthropic format
        messages = []
        system_message = ""
        
        # Handle system prompt
        if session.system_prompt.strip():
            system_message = session.system_prompt
        
        # Add conversation messages (only enabled ones)
        for msg in session.messages:
            if msg.enabled:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
        
        # Build request payload
        payload = {
            "model": session.model,
            "messages": messages,
            "max_tokens": session.params.get("max_tokens", 1000)
        }
        
        # Add system message if provided
        if system_message:
            payload["system"] = system_message
        
        # Add parameters
        if "temperature" in session.params:
            payload["temperature"] = session.params["temperature"]
        
        if "top_p" in session.params:
            payload["top_p"] = session.params["top_p"]
        
        return payload
    
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Anthropic API response"""
        try:
            if "error" in response:
                return {
                    "id": "",
                    "content": "",
                    "status": "error",
                    "error": response["error"].get("message", "Unknown error"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "time_taken": 0
                }
            
            content = ""
            if "content" in response and len(response["content"]) > 0:
                content = response["content"][0].get("text", "")
            
            usage = response.get("usage", {})
            
            return {
                "id": response.get("id", ""),
                "content": content,
                "status": "success",
                "error": None,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "time_taken": 0  # Anthropic doesn't provide timing info
            }
        
        except Exception as e:
            return {
                "id": "",
                "content": "",
                "status": "error",
                "error": f"Error parsing response: {str(e)}",
                "input_tokens": 0,
                "output_tokens": 0,
                "time_taken": 0
            }
    
    def make_request(self, session, raw_messages=None) -> Dict[str, Any]:
        """Make API call to Anthropic"""
        try:
            payload = self.build_request(session)
            
            response = requests.post(
                f"{self.base_url}/messages",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            response_data = response.json()
            
            if response.status_code != 200:
                return {
                    "error": {
                        "message": response_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    }
                }
            
            return response_data
        
        except requests.exceptions.RequestException as e:
            return {
                "error": {
                    "message": f"Request failed: {str(e)}"
                }
            }
        except Exception as e:
            return {
                "error": {
                    "message": f"Unexpected error: {str(e)}"
                }
            }
