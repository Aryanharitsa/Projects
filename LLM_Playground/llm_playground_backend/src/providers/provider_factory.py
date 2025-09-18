import os
from typing import Optional, Dict, Any
from src.providers.base_provider import BaseProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.august_provider import AugustProvider

class ProviderFactory:
    """Factory class for creating LLM providers"""
    
    @staticmethod
    def create_provider(provider_name: str) -> Optional[BaseProvider]:
        """Create a provider instance based on the provider name"""
        provider_name = provider_name.lower()
        
        if provider_name == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            return OpenAIProvider(api_key)
        
        elif provider_name == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            return AnthropicProvider(api_key)
        
        elif provider_name == "google":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment variables")
            return GeminiProvider(api_key)
        
        elif provider_name == "august":
            api_key = os.getenv("AUGUST_API_KEY", "")  # August API key is optional
            base_url = os.getenv("AUGUST_API_BASE_URL")
            if not base_url:
                raise ValueError("AUGUST_API_BASE_URL not found in environment variables")
            return AugustProvider(api_key, base_url)
        
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    @staticmethod
    def get_available_providers() -> Dict[str, bool]:
        """Get list of available providers based on API keys"""
        providers = {
            "OpenAI": bool(os.getenv("OPENAI_API_KEY")),
            "Anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "Google": bool(os.getenv("GEMINI_API_KEY")),
            "August": bool(os.getenv("AUGUST_API_BASE_URL"))  # August only needs base URL
        }
        return providers
    
    @staticmethod
    def validate_provider_setup(provider_name: str) -> tuple[bool, str]:
        """Validate if a provider is properly set up"""
        try:
            provider = ProviderFactory.create_provider(provider_name)
            return True, "Provider setup is valid"
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    def get_provider(self, provider_name: str) -> Optional[BaseProvider]:
        """
        Instance wrapper for create_provider to fetch a provider by name.
        """
        return ProviderFactory.create_provider(provider_name)
