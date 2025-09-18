import requests
import json
from typing import Dict, Any, List
from src.providers.base_provider import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini API provider implementation"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    def get_models(self) -> List[str]:
        """Return list of available Gemini models"""
        return [
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro"
        ]
    
    def get_parameters(self) -> List[str]:
        """Return list of supported parameters"""
        return ["temperature", "top_k", "top_p", "max_tokens"]
    
    def supports_json_mode(self) -> bool:
        """Gemini doesn't have explicit JSON mode"""
        return False
    
    def supports_reasoning_effort(self) -> bool:
        """Gemini doesn't support reasoning effort"""
        return False
    
    def build_request(self, session) -> Dict[str, Any]:
        """Build Gemini API request payload"""
        # Convert messages to Gemini format
        contents = []
        
        # Add system instruction if provided
        system_instruction = None
        if session.system_prompt.strip():
            system_instruction = {
                "parts": [{"text": session.system_prompt}]
            }
        
        # Add conversation messages (only enabled ones)
        for msg in session.messages:
            if msg.enabled:
                # Gemini uses "user" and "model" instead of "user" and "assistant"
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })
        
        # Build request payload
        payload = {
            "contents": contents
        }
        
        # Add system instruction if provided
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        
        # Build generation config
        generation_config = {}
        
        if "temperature" in session.params:
            generation_config["temperature"] = session.params["temperature"]
        
        if "top_k" in session.params:
            generation_config["topK"] = int(session.params["top_k"])
        
        if "top_p" in session.params:
            generation_config["topP"] = session.params["top_p"]
        
        if "max_tokens" in session.params:
            generation_config["maxOutputTokens"] = int(session.params["max_tokens"])
        
        if generation_config:
            payload["generationConfig"] = generation_config
        
        return payload
    
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gemini API response"""
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
            if "candidates" in response and len(response["candidates"]) > 0:
                candidate = response["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        content = parts[0]["text"]
            
            # Extract token usage if available
            usage_metadata = response.get("usageMetadata", {})
            
            return {
                "id": "",  # Gemini doesn't provide response ID
                "content": content,
                "status": "success",
                "error": None,
                "input_tokens": usage_metadata.get("promptTokenCount", 0),
                "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
                "time_taken": 0  # Gemini doesn't provide timing info
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
        """Make API call to Gemini"""
        try:
            payload = self.build_request(session)
            
            # Build URL with API key
            url = f"{self.base_url}/models/{session.model}:generateContent"
            params = {"key": self.api_key}
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url,
                headers=headers,
                params=params,
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

