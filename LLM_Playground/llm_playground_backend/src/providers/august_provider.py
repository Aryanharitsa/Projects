import requests
import json
import os
from typing import Dict, Any, List
from src.providers.base_provider import BaseProvider


class AugustProvider(BaseProvider):
    """August Service API provider implementation"""
    
    def __init__(self, api_key: str, base_url: str = None):
        super().__init__(api_key)
        self.base_url = base_url or os.getenv("AUGUST_API_BASE_URL", "http://localhost:8000")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        } if self.api_key else {
            "Content-Type": "application/json"
        }
    
    def get_models(self) -> List[str]:
        """August service doesn't expose model selection - it's handled server-side"""
        return ["august-default"]
    
    def get_parameters(self) -> List[str]:
        """Return list of supported parameters for August service"""
        return ["temperature", "max_tokens", "json_mode"]
    
    def supports_json_mode(self) -> bool:
        """August service supports JSON mode"""
        return True
    
    def supports_reasoning_effort(self) -> bool:
        """August service doesn't support reasoning effort"""
        return False
    
    def build_request(self, session) -> Dict[str, Any]:
        """Build August API request payload"""
        # Convert messages to August format
        messages = []
        
        # Add conversation messages (only enabled ones)
        for msg in session.messages:
            if msg.enabled:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
        
        # Build request payload according to August API spec
        payload = {
            "process_type": "dialogue",
            "request_type": "create_august_response",
            "pkey": session.pkey or "default_expert",
            "pvariables": session.pvariables or {},
            "messages": messages,
            "json_mode": session.json_mode
        }
        
        # Add optional parameters
        if "temperature" in session.params:
            payload["temperature"] = session.params["temperature"]
        
        if "max_tokens" in session.params:
            payload["max_tokens"] = session.params["max_tokens"]
        
        # Add user_id and tenant_id if available
        payload["user_id"] = "playground_user"
        payload["tenant_id"] = "1"
        
        # Add trace information
        import uuid
        payload["trace_id"] = str(uuid.uuid4())
        payload["generation_name"] = "playground_generation"
        
        return payload
    
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse August API response"""
        try:
            if "error" in response:
                return {
                    "id": "",
                    "content": "",
                    "status": "error",
                    "error": response.get("error", "Unknown error"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "time_taken": 0,
                    "safeguard_violation": False,
                    "safeguard_phrase": None
                }
            
            # August API response format
            return {
                "id": response.get("id", ""),
                "content": response.get("content", ""),
                "status": response.get("status", "unknown"),
                "error": response.get("error"),
                "input_tokens": response.get("input_tokens", 0),
                "output_tokens": response.get("output_tokens", 0),
                "time_taken": response.get("time_taken", 0),
                "safeguard_violation": response.get("safeguard_violation", False),
                "safeguard_phrase": response.get("safeguard_phrase")
            }
        
        except Exception as e:
            return {
                "id": "",
                "content": "",
                "status": "error",
                "error": f"Error parsing response: {str(e)}",
                "input_tokens": 0,
                "output_tokens": 0,
                "time_taken": 0,
                "safeguard_violation": False,
                "safeguard_phrase": None
            }
    
    def make_request(self, session) -> Dict[str, Any]:
        """Make API call to August service"""
        try:
            payload = self.build_request(session)
            
            # Make request to August service
            response = requests.post(
                f"{self.base_url}/api/generate",  # Adjust endpoint as needed
                headers=self.headers,
                json=payload,
                timeout=120  # August service might take longer
            )
            
            response_data = response.json()
            
            if response.status_code != 200:
                return {
                    "error": response_data.get("error", f"HTTP {response.status_code}"),
                    "status": "error"
                }
            
            return response_data
        
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Request failed: {str(e)}",
                "status": "error"
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}",
                "status": "error"
            }

