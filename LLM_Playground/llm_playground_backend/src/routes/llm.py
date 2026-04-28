from flask import Blueprint, request, jsonify
from flask import current_app
import os, json, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, List
import traceback  # Add this import at the top if not already present
import requests

#
from src.models.user import User
from src.providers.provider_factory import ProviderFactory
from src.pricing import estimate_cost, get_pricing_table
from src.judge import DEFAULT_RUBRIC, judge_compare

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

        in_tok  = response.get('input_tokens', 0) or 0
        out_tok = response.get('output_tokens', 0) or 0
        return jsonify({
            'success': True,
            'response': response.get('content', ''),
            'debug_info': {
                'provider': provider_name,
                'model': model,
                'input_tokens': in_tok,
                'output_tokens': out_tok,
                'total_tokens': in_tok + out_tok,
                'latency': round(latency, 3),
                'cost_usd': estimate_cost(model, in_tok, out_tok),
                'timestamp': end_time.isoformat(),
                'request_id': str(uuid.uuid4()),
                'status': response.get('status', 'success'),
                'model_version': response.get('model_version', model)
            },
            'raw_response': response
        })
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        current_app.logger.error(traceback_str)
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback_str
        }), 500

@llm_bp.route('/pricing', methods=['GET'])
def get_pricing():
    """Expose the per-1M-token pricing table consumed by the Arena UI."""
    return jsonify({'success': True, 'pricing': get_pricing_table()})


def _run_candidate(candidate: Dict[str, Any],
                   messages: List[Dict[str, Any]],
                   system_prompt: str) -> Dict[str, Any]:
    """Execute a single candidate run for /compare and normalise its result."""
    provider_name = candidate.get('provider') or ''
    model = candidate.get('model') or ''
    started = datetime.now()
    try:
        provider_instance = provider_factory.create_provider(provider_name)
        if not provider_instance:
            raise ValueError(f'Provider {provider_name} not available')

        msgs = messages[:]
        if system_prompt:
            msgs = [{"role": "system", "content": system_prompt}] + msgs

        resp = provider_instance.make_request(model, msgs)
        latency = (datetime.now() - started).total_seconds()

        in_tok  = resp.get('input_tokens', 0) or 0
        out_tok = resp.get('output_tokens', 0) or 0
        status  = resp.get('status', 'success')
        error   = resp.get('error')
        # Some providers return {"error": {...}} when the call fails upstream.
        if status != 'success' or (isinstance(error, dict) and error):
            err_msg = (
                error.get('message') if isinstance(error, dict)
                else (error or 'Upstream provider error')
            )
            return {
                'provider': provider_name,
                'model': model,
                'status': 'error',
                'error': err_msg,
                'response': '',
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'latency': round(latency, 3),
                'cost_usd': 0.0,
                'model_version': model,
            }

        return {
            'provider': provider_name,
            'model': model,
            'status': 'success',
            'error': None,
            'response': resp.get('content', ''),
            'input_tokens': in_tok,
            'output_tokens': out_tok,
            'total_tokens': in_tok + out_tok,
            'latency': round(latency, 3),
            'cost_usd': estimate_cost(model, in_tok, out_tok),
            'model_version': resp.get('model_version', model),
        }
    except Exception as e:  # noqa: BLE001 — surface as a typed result, don't crash siblings
        latency = (datetime.now() - started).total_seconds()
        return {
            'provider': provider_name,
            'model': model,
            'status': 'error',
            'error': str(e),
            'response': '',
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'latency': round(latency, 3),
            'cost_usd': 0.0,
            'model_version': model,
        }


@llm_bp.route('/compare', methods=['POST'])
def compare():
    """Fan-out the same prompt to multiple provider/model candidates in parallel.

    Request body:
        {
          "candidates": [ {"provider": "OpenAI", "model": "gpt-4o"}, ... ],
          "messages":   [ {"role": "user", "content": "..."}, ... ],
          "system_prompt": "optional",
          "params": { ... unused for now, reserved }
        }
    """
    try:
        data = request.get_json() or {}
        candidates = data.get('candidates') or []
        messages   = data.get('messages') or []
        system_prompt = data.get('system_prompt', '') or ''

        if not candidates:
            return jsonify({'success': False, 'error': 'No candidates provided'}), 400
        if not messages:
            return jsonify({'success': False, 'error': 'No messages provided'}), 400
        # Sanity cap — parallelism is cheap, but keep rogue payloads in check.
        if len(candidates) > 8:
            return jsonify({'success': False, 'error': 'Too many candidates (max 8)'}), 400

        # Preserve only role/content for downstream providers.
        clean_messages = [
            {'role': m.get('role', 'user'), 'content': m.get('content', '')}
            for m in messages
            if m.get('enabled', True)
        ]

        started = datetime.now()
        with ThreadPoolExecutor(max_workers=min(len(candidates), 8)) as pool:
            results = list(pool.map(
                lambda c: _run_candidate(c, clean_messages, system_prompt),
                candidates,
            ))
        total_latency = round((datetime.now() - started).total_seconds(), 3)

        successes = [r for r in results if r['status'] == 'success']
        winners = {}
        if successes:
            winners['fastest']     = min(successes, key=lambda r: r['latency'])['model']
            winners['cheapest']    = min(successes, key=lambda r: r['cost_usd'])['model']
            winners['most_verbose'] = max(successes, key=lambda r: r['output_tokens'])['model']

        return jsonify({
            'success': True,
            'results': results,
            'winners': winners,
            'wall_latency': total_latency,
            'request_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/rubric', methods=['GET'])
def get_default_rubric():
    """Expose the default judge rubric so the UI can pre-populate its editor."""
    return jsonify({'success': True, 'rubric': DEFAULT_RUBRIC})


@llm_bp.route('/judge', methods=['POST'])
def judge():
    """Score a set of Arena responses with an LLM-as-judge.

    Request body:
        {
          "prompt":        "<user prompt that produced the responses>",
          "system_prompt": "<optional original system prompt>",
          "candidates":    [ {provider, model, response, status?}, ... ],
          "judge":         { "provider": "Anthropic", "model": "claude-..." },
          "rubric":        [ {name, description, weight}, ... ]   # optional
        }
    """
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or '').strip()
        system_prompt = data.get('system_prompt') or ''
        candidates = data.get('candidates') or []
        rubric = data.get('rubric')
        judge_cfg = data.get('judge') or {}

        # Only score successful candidates against their actual response;
        # surface failed ones with an empty body so they appear in the verdict
        # list (and naturally land at the bottom of the leaderboard).
        scoreable = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            scoreable.append({
                'provider': c.get('provider', ''),
                'model':    c.get('model', ''),
                'response': c.get('response', '') if c.get('status', 'success') == 'success' else '',
                'status':   c.get('status', 'success'),
            })

        if len(scoreable) < 1:
            return jsonify({'success': False, 'error': 'No candidates provided'}), 400

        judge_provider = (judge_cfg.get('provider') or '').strip()
        judge_model = (judge_cfg.get('model') or '').strip()
        if not judge_provider or not judge_model:
            return jsonify({'success': False, 'error': 'judge.provider and judge.model are required'}), 400

        payload, status = judge_compare(
            user_prompt=prompt,
            system_prompt=system_prompt,
            candidates=scoreable,
            judge_provider_name=judge_provider,
            judge_model=judge_model,
            rubric=rubric,
            provider_factory=provider_factory,
        )
        return jsonify(payload), status
    except Exception as e:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


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
