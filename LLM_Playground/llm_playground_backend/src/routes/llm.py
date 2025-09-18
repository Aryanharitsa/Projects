from flask import Blueprint, request, jsonify
from flask import current_app
import os, json, uuid
from datetime import datetime
from typing import Dict, Any, List
import traceback  # Add this import at the top if not already present
import requests
from datetime import datetime

#
from src.models.user import User
from src.providers.provider_factory import ProviderFactory

llm_bp = Blueprint('llm', __name__)

# Initialize provider factory
provider_factory = ProviderFactory()

@llm_bp.route('/providers', methods=['GET'])
def get_providers():
    """Get available providers and their status"""
    try:
        providers = provider_factory.get_available_providers()
        provider_status = {}
        
        for provider_name in ['OpenAI', 'Anthropic', 'Google', 'August']:
            provider_status[provider_name] = {
                'available': provider_name in providers,
                'models': providers.get(provider_name, {}).get('models', []) if provider_name in providers else []
            }
        
        return jsonify({
            'success': True,
            'providers': provider_status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@llm_bp.route('/models/<provider>', methods=['GET'])
def get_models(provider):
    """Get available models for a specific provider"""
    provider_instance = provider_factory.create_provider(provider)
    if not provider_instance:
        return jsonify({'error': f'Provider {provider} not available'}), 404

    try:
        models = provider_instance.get_models()
    except Exception as e:
        current_app.logger.error(f"Error fetching models for {provider}: {e}")
        # Fallback to an empty list if something goes wrong
        models = []

    # Return the list of model IDs wrapped in a JSON object
    return jsonify({'models': models}), 200

@llm_bp.route('/parameters/<provider>', methods=['GET'])
def get_parameters(provider):
    """Get available parameters for a specific provider"""
    try:
        provider_instance = provider_factory.create_provider(provider)
        if not provider_instance:
            return jsonify({
                'success': False,
                'error': f'Provider {provider} not available'
            }), 404
        
        parameters = provider_instance.get_parameters()
        return jsonify({
            'success': True,
            'parameters': parameters,
            'supports_json_mode': provider_instance.supports_json_mode(),
            'supports_reasoning_effort': provider_instance.supports_reasoning_effort()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@llm_bp.route('/chat', methods=['POST'])
def chat():
    """Process chat request and return response"""
    try:
        data = request.get_json()
        current_app.logger.debug(f"Chat request data: {data}")
        
        # Handle August mode
        if data.get('pkey') or data.get('process_type'):
            august_url = os.getenv('AUGUST_SERVICE_URL')
            token = os.getenv('AUGUST_API_KEY')
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            # Forward request to August service
            aug_resp = requests.post(
                f"{august_url}/create_august_response",
                headers=headers,
                json=data,
                timeout=60
            )
            aug_data = aug_resp.json()
            current_app.logger.debug(f"August raw response: {aug_data}")

            # Build and return payload for frontend
            return jsonify({
                'success': aug_data.get('status') == 'success',
                'response': aug_data.get('content', ''),
                'debug_info': {
                    'provider':      'August',
                    'model':         data.get('pkey'),
                    'pkey':          data.get('pkey'),
                    'pvariables':    data.get('pvariables', {}),
                    'input_tokens':  aug_data.get('input_tokens', 0),
                    'output_tokens': aug_data.get('output_tokens', 0),
                    'total_tokens':  aug_data.get('input_tokens', 0) + aug_data.get('output_tokens', 0),
                    'latency':       aug_data.get('time_taken', 0),
                    'timestamp':     aug_data.get('timestamp', datetime.utcnow().isoformat()),
                    'request_id':    aug_data.get('id', str(uuid.uuid4())),
                    'status':        aug_data.get('status', 'success'),
                    'model_version': aug_data.get('model_version', 'August')
                },
                'raw_response': aug_data
            })
        
        # Validate required fields for universal mode
        required_fields = ['provider', 'model', 'messages']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        provider_name = data['provider']
        model = data['model']
        raw_messages = data['messages']

        system_prompt = data.get('system_prompt', '')
        if system_prompt:
            # Insert system prompt at the front as a system message
            raw_messages = [{"role": "system", "content": system_prompt}] + raw_messages

        # Get provider and make request
        provider_instance = provider_factory.create_provider(provider_name)
        if not provider_instance:
            return jsonify({
                'success': False,
                'error': f'Provider {provider_name} not available'
            }), 404

        # Make the API call
        start_time = datetime.now()
        response = provider_instance.make_request(model, raw_messages)
        end_time = datetime.now()

        # Calculate metrics
        latency = (end_time - start_time).total_seconds()

        return jsonify({
            'success': True,
            'response': response.get('content', ''),
            'debug_info': {
                'provider': provider_name,
                'model': model,
                'input_tokens': response.get('input_tokens', 0),
                'output_tokens': response.get('output_tokens', 0),
                'total_tokens': response.get('input_tokens', 0) + response.get('output_tokens', 0),
                'latency': round(latency, 3),
                'timestamp': end_time.isoformat(),
                'request_id': str(uuid.uuid4()),
                'status': response.get('status', 'success'),
                'model_version': response.get('model_version', model)
            },
            'raw_response': response
        })
        current_app.logger.debug(f"Chat response raw: {response}")
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        current_app.logger.error(traceback_str)
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback_str
        }), 500

@llm_bp.route('/august/upload', methods=['POST'])
def upload_august_json():
    """Upload and parse August service JSON"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Parse JSON content
        try:
            content = file.read().decode('utf-8')
            august_data = json.loads(content)
        except json.JSONDecodeError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid JSON format: {str(e)}'
            }), 400
        
        # Extract relevant data from August JSON
        extracted_data = {
            'process_type': august_data.get('process_type', ''),
            'user_id': august_data.get('user_id', ''),
            'pkey': august_data.get('pkey', ''),
            'pvariables': august_data.get('pvariables', {}),
            'messages': august_data.get('messages', []),
            'temperature': august_data.get('temperature'),
            'max_tokens': august_data.get('max_tokens'),
            'request_type': august_data.get('request_type', ''),
            'generation_name': august_data.get('generation_name', ''),
            'json_mode': august_data.get('json_mode', False)
        }
        
        return jsonify({
            'success': True,
            'data': extracted_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@llm_bp.route('/export', methods=['POST'])
def export_chat():
    """Export chat session as JSON"""
    try:
        data = request.get_json()
        
        export_data = {
            'provider': data.get('provider'),
            'model': data.get('model'),
            'params': data.get('params', {}),
            'system_prompt': data.get('system_prompt', ''),
            'messages': data.get('messages', []),
            'response': data.get('response', ''),
            'timestamp': datetime.now().isoformat(),
            'export_id': str(uuid.uuid4())
        }
        
        return jsonify({
            'success': True,
            'data': export_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@llm_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })
