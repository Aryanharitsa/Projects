import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, List
from src.providers.base_provider import BaseProvider
from src.models import User  # Placeholder import if needed
import logging
logger = logging.getLogger(__name__)

class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def get_models(self) -> List[str]:
        """Fetch available OpenAI models dynamically."""
        logger.debug(f"OpenAIProvider fetching models from {self.base_url}/models")
        try:
            response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=30)
            logger.debug(f"OpenAIProvider response status: {response.status_code}")
            try:
                data = response.json()
                logger.debug(f"OpenAIProvider response JSON keys: {list(data.keys())}")
            except Exception as e:
                logger.error("Failed to parse models response JSON", exc_info=e)
                raise
            if response.status_code != 200 or "data" not in data:
                logger.error(f"Failed to fetch models: {data}")
                # Fallback list
                fallback_models = [
                    "gpt-4", "gpt-4-turbo", "gpt-4-turbo-preview",
                    "gpt-3.5-turbo", "gpt-3.5-turbo-16k",
                    "o1-preview", "o1-mini", "o3-mini",
                    "gpt-4.1", "gpt-4.5", "gpt-4o", "o3-preview", "gpt-4o-mini"
                ]
                logger.debug(f"OpenAIProvider fallback models: {fallback_models}")
                return fallback_models
            # Successful fetch
            dynamic_models = [m["id"] for m in data["data"]]
            logger.debug(f"OpenAIProvider dynamic models: {dynamic_models}")
            return dynamic_models
        except Exception as e:
            logger.error("Error fetching OpenAI models", exc_info=e)
            # Fallback list on exception
            fallback_models = [
                "gpt-4", "gpt-4-turbo", "gpt-4-turbo-preview",
                "gpt-3.5-turbo", "gpt-3.5-turbo-16k",
                "o1-preview", "o1-mini", "o3-mini",
                "gpt-4.1", "gpt-4.5", "gpt-4o", "o3-preview", "gpt-4o-mini"
            ]
            logger.debug(f"OpenAIProvider fallback models on exception: {fallback_models}")
            return fallback_models
    
    def get_parameters(self) -> List[str]:
        """Return list of supported parameters"""
        return ["temperature", "top_p", "max_completion_tokens", "reasoning_effort"]
    
    def supports_json_mode(self) -> bool:
        """OpenAI supports JSON mode"""
        return True
    
    def supports_reasoning_effort(self) -> bool:
        """OpenAI supports reasoning effort for o1/o3 models"""
        return True
    
    def build_request(self, session) -> Dict[str, Any]:
        """Build OpenAI API request payload"""
        # Convert messages to OpenAI format
        messages = []
        
        # Add system message if provided
        if session.system_prompt.strip():
            messages.append({
                "role": "system",
                "content": session.system_prompt
            })
        
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
            "messages": messages
        }
        
        # Add parameters
        if "temperature" in session.params:
            payload["temperature"] = session.params["temperature"]
        
        if "top_p" in session.params:
            payload["top_p"] = session.params["top_p"]
        
        if "max_tokens" in session.params:
            payload["max_tokens"] = session.params["max_tokens"]
        
        # Support new completion token limit parameter
        if "max_completion_tokens" in session.params:
            payload["max_completion_tokens"] = session.params["max_completion_tokens"]
        
        # Add reasoning effort for o1/o3 models
        if session.model.startswith(('o1', 'o3')) and "reasoning_effort" in session.params:
            payload["reasoning_effort"] = session.params["reasoning_effort"]
        
        # Add JSON mode if enabled
        if session.json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        return payload
    
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenAI API response"""
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
            
            choice = response["choices"][0]
            usage = response.get("usage", {})
            
            return {
                "id": response.get("id", ""),
                "content": choice["message"]["content"],
                "status": "success",
                "error": None,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "time_taken": 0  # OpenAI doesn't provide timing info
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
    
    def make_request(self, model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Make API call to OpenAI"""
        import os
        print("🔑 OpenAI API KEY being used:", os.environ.get("OPENAI_API_KEY"))
        try:
            start_time = time.time()
            payload = {
                "model": model,
                "messages": messages
            }
            logger.debug(f"OpenAIProvider request payload: {json.dumps(payload)}")
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )

            response_data = response.json()
            logger.debug(f"OpenAIProvider raw response: {json.dumps(response_data)}")
            logger.debug(f"OpenAIProvider parsed response_data: {json.dumps(response_data)}")
            elapsed = round(time.time() - start_time, 3)

            if response.status_code != 200:
                return {
                    "id": "",
                    "content": "",
                    "status": "error",
                    "error": response_data.get("error", {}).get("message", f"HTTP {response.status_code}"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "time_taken": elapsed,
                    "timestamp": datetime.utcnow().isoformat(),
                    "model_version": model
                }

            parsed = self.parse_response(response_data)
            parsed["time_taken"] = elapsed
            parsed["timestamp"] = datetime.utcnow().isoformat()
            parsed["model_version"] = response_data.get("model", model)
            logger.debug(f"OpenAIProvider returning parsed result: {parsed}")
            return parsed

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
