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
from src.judge import DEFAULT_RUBRIC, judge_compare, judge_consensus_compare
from src import history
from src import vote_arena
from src import prompts as prompts_lib
from src import insights as insights_lib
from src import evals as evals_lib
from src import rubrics as rubrics_lib
from src import optimizer as optimizer_lib
from src import adversary as adversary_lib
from src import showdown as showdown_lib
from src import drift as drift_lib
from src import surgeon as surgeon_lib
from src import frontier as frontier_lib
from src import relay as relay_lib
from src import sentinel as sentinel_lib
from src import cache as cache_lib

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

        run_id = str(uuid.uuid4())
        arena_payload = {
            'success': True,
            'results': results,
            'winners': winners,
            'wall_latency': total_latency,
            'request_id': run_id,
            'timestamp': datetime.utcnow().isoformat(),
        }

        # Persist to history. The prompt of record is the last user message
        # in the chain; downstream we surface it as the "row title".
        prompt_for_history = next(
            (m.get('content', '') for m in reversed(clean_messages) if m.get('role') == 'user'),
            '',
        )
        try:
            history.save_run(arena_payload, prompt=prompt_for_history, system_prompt=system_prompt)
        except Exception as save_err:  # noqa: BLE001
            # Persistence is best-effort — never let a logging issue 500 the run.
            current_app.logger.warning(f"history.save_run failed: {save_err}")

        # If the request was launched from a Prompt Library version, link
        # the run back so the library's per-version stats reflect it.
        prompt_version_id = (data.get('prompt_version_id') or '').strip() or None
        if prompt_version_id:
            try:
                prompts_lib.link_run(run_id, prompt_version_id)
            except Exception as link_err:  # noqa: BLE001
                current_app.logger.warning(f"prompts.link_run failed: {link_err}")

        return jsonify(arena_payload)
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

        # If the client passed a `run_id`, retro-attach this verdict to the
        # persisted Arena run so /history surfaces it. Best-effort — a missing
        # row (e.g. because the run was deleted mid-judging) is non-fatal.
        run_id = (data.get('run_id') or '').strip() or None
        if status == 200 and payload.get('success') and run_id:
            try:
                history.update_judge(run_id, payload)
            except Exception as save_err:  # noqa: BLE001
                current_app.logger.warning(f"history.update_judge failed: {save_err}")

        return jsonify(payload), status
    except Exception as e:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/judge/consensus', methods=['POST'])
def judge_consensus():
    """Score a set of Arena responses with a **panel** of K LLM judges.

    Fans the same judge prompt out to every judge in parallel, then folds
    their verdicts into a consensus leaderboard with confidence bars, an
    inter-judge agreement card (Fleiss' kappa per criterion + overall mean
    composite std), and a per-judge agreement-with-panel breakdown.

    Request body:
        {
          "prompt":        "<user prompt that produced the responses>",
          "system_prompt": "<optional original system prompt>",
          "candidates":    [ {provider, model, response, status?}, ... ],
          "judges":        [ {provider, model}, ... ]    # ≥ 2
          "rubric":        [ {name, description, weight}, ... ]  # optional
          "run_id":        "<existing arena run id>"             # optional
        }
    """
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or '').strip()
        system_prompt = data.get('system_prompt') or ''
        candidates = data.get('candidates') or []
        rubric = data.get('rubric')
        judges_in = data.get('judges') or []

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

        # Clean judge list — drop empties and duplicates while preserving order.
        seen = set()
        judges = []
        for j in judges_in:
            if not isinstance(j, dict):
                continue
            prov = (j.get('provider') or '').strip()
            mdl = (j.get('model') or '').strip()
            if not prov or not mdl:
                continue
            key = f"{prov}:{mdl}"
            if key in seen:
                continue
            seen.add(key)
            judges.append({'provider': prov, 'model': mdl})

        if len(judges) < 2:
            return jsonify({
                'success': False,
                'error':   'Need at least 2 distinct judges for consensus (provider+model pair)',
            }), 400

        payload, status = judge_consensus_compare(
            user_prompt=prompt,
            system_prompt=system_prompt,
            candidates=scoreable,
            judges=judges,
            rubric=rubric,
            provider_factory=provider_factory,
        )

        # Attach consensus to the persisted Arena run so History surfaces it.
        run_id = (data.get('run_id') or '').strip() or None
        if status == 200 and payload.get('success') and run_id:
            try:
                history.update_consensus(run_id, payload)
            except Exception as save_err:  # noqa: BLE001
                current_app.logger.warning(f"history.update_consensus failed: {save_err}")

        return jsonify(payload), status
    except Exception as e:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Run history — every Arena/Judge run is persisted; these endpoints power
# the History tab (list / detail / tag / star / delete / stats / diff).
# ---------------------------------------------------------------------------

@llm_bp.route('/history', methods=['GET'])
def history_list():
    """List runs with optional filtering. Filters compose with AND semantics.

    Query params:
        q            substring match across prompt / system / model fingerprint
        model        substring match in the comma-joined model list
        provider     match runs that included this provider
        judged       "1" → only runs with an LLM-as-judge result
        starred      "1" → only starred runs
        tag          exact tag match
        since        unix epoch (float)
        before       unix epoch (float)
        limit        page size (default 50, max 500)
        offset       row offset
    """
    args = request.args

    def _bool_arg(name: str) -> bool:
        v = args.get(name, '').strip().lower()
        return v in ('1', 'true', 'yes', 'on')

    def _float_arg(name: str):
        v = args.get(name)
        if v in (None, ''):
            return None
        try:
            return float(v)
        except ValueError:
            return None

    rows, total = history.list_runs(
        q=(args.get('q') or '').strip() or None,
        model=(args.get('model') or '').strip() or None,
        provider=(args.get('provider') or '').strip() or None,
        judged_only=_bool_arg('judged'),
        starred_only=_bool_arg('starred'),
        tag=(args.get('tag') or '').strip() or None,
        since=_float_arg('since'),
        before=_float_arg('before'),
        limit=int(args.get('limit', 50) or 50),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'runs': rows, 'total': total})


@llm_bp.route('/history/stats', methods=['GET'])
def history_stats():
    """Aggregate dashboard metrics across the whole history."""
    return jsonify({'success': True, 'stats': history.stats()})


@llm_bp.route('/history/diff', methods=['POST'])
def history_diff():
    """Side-by-side diff of two runs. Body: `{a: <run_id>, b: <run_id>}`."""
    data = request.get_json() or {}
    a = (data.get('a') or '').strip()
    b = (data.get('b') or '').strip()
    if not a or not b:
        return jsonify({'success': False, 'error': 'a and b are required'}), 400
    if a == b:
        return jsonify({'success': False, 'error': 'a and b must be different runs'}), 400
    result = history.diff(a, b)
    if result is None:
        return jsonify({'success': False, 'error': 'one or both runs not found'}), 404
    return jsonify({'success': True, 'diff': result})


@llm_bp.route('/history/<run_id>', methods=['GET'])
def history_get(run_id):
    run = history.get_run(run_id)
    if not run:
        return jsonify({'success': False, 'error': 'run not found'}), 404
    return jsonify({'success': True, 'run': run})


@llm_bp.route('/history/<run_id>', methods=['DELETE'])
def history_delete(run_id):
    if not history.delete_run(run_id):
        return jsonify({'success': False, 'error': 'run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/history/<run_id>/meta', methods=['POST'])
def history_set_meta(run_id):
    """Update tag / note / starred on a run."""
    data = request.get_json() or {}
    tag = data.get('tag')
    note = data.get('note')
    starred = data.get('starred')
    if tag is None and note is None and starred is None:
        return jsonify({'success': False, 'error': 'no updatable field'}), 400
    if not history.set_meta(
        run_id,
        tag=tag if isinstance(tag, str) else None,
        note=note if isinstance(note, str) else None,
        starred=bool(starred) if starred is not None else None,
    ):
        return jsonify({'success': False, 'error': 'run not found'}), 404
    return jsonify({'success': True, 'run': history.get_run(run_id)})


# ---------------------------------------------------------------------------
# Personal Chatbot Arena — blind A/B voting + ELO leaderboard.
# Round-4 move (Day 18). Pairs are sampled from the persisted run history,
# votes feed an ELO replay, and judge-vs-human agreement is computed
# server-side from the same vote log.
# ---------------------------------------------------------------------------


@llm_bp.route('/arena/pair', methods=['GET'])
def arena_pair():
    """Return a blind A/B pair to vote on.

    Optional query params:
        run_id        — sample within this specific run (deeplink from History).
        exclude_a     — model key already shown as A (de-duplicate refreshes).
        exclude_b     — model key already shown as B.

    Server keeps the truth in the response under `_truth` so the subsequent
    POST /arena/vote can echo it back; the frontend never reveals A/B
    identities until after the vote is cast (it strips _truth from the visible
    DOM but keeps it in component state).
    """
    args = request.args
    run_id = (args.get('run_id') or '').strip() or None
    exclude_a = (args.get('exclude_a') or '').strip() or None
    exclude_b = (args.get('exclude_b') or '').strip() or None
    exclude_pairs = []
    if exclude_a and exclude_b:
        exclude_pairs.append((exclude_a, exclude_b))
    pair = vote_arena.pick_pair(run_id=run_id, exclude_pairs=exclude_pairs)
    if not pair:
        return jsonify({'success': False, 'error': 'no votable pair available — run an Arena first'}), 404
    return jsonify({'success': True, 'pair': pair})


@llm_bp.route('/arena/vote', methods=['POST'])
def arena_vote():
    """Record a vote.

    Body: {
      run_id, model_a, model_b, winner ('a'|'b'|'tie'|'both_bad'),
      voter?, judge_winner?, prompt_hash?, prompt_preview?,
      latency_a?, latency_b?, cost_a?, cost_b?
    }

    Returns the updated leaderboard so the UI can show ΔELO chips for the
    two models without a follow-up request.
    """
    data = request.get_json() or {}
    vote_id = vote_arena.record_vote(
        run_id=(data.get('run_id') or '').strip(),
        model_a=(data.get('model_a') or '').strip(),
        model_b=(data.get('model_b') or '').strip(),
        winner=(data.get('winner') or '').strip(),
        voter=(data.get('voter') or '').strip() or None,
        judge_winner=(data.get('judge_winner') or '').strip() or None,
        prompt_hash=(data.get('prompt_hash') or '').strip() or None,
        prompt_preview=(data.get('prompt_preview') or '').strip() or None,
        latency_a=data.get('latency_a'),
        latency_b=data.get('latency_b'),
        cost_a=data.get('cost_a'),
        cost_b=data.get('cost_b'),
    )
    if not vote_id:
        return jsonify({'success': False, 'error': 'invalid vote payload'}), 400
    lb = vote_arena.leaderboard()
    return jsonify({
        'success': True,
        'vote_id': vote_id,
        'leaderboard': lb['ratings'],
        'meta': lb['meta'],
    })


@llm_bp.route('/arena/vote/<vote_id>', methods=['DELETE'])
def arena_vote_delete(vote_id):
    """Undo a vote (e.g. misclick). The leaderboard is replayed every time
    so deleting a vote rewinds it cleanly."""
    if not vote_arena.delete_vote(vote_id):
        return jsonify({'success': False, 'error': 'vote not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/arena/leaderboard', methods=['GET'])
def arena_leaderboard():
    """Replay-derived ELO leaderboard.

    Optional query params:
        k          — K-factor override (default $LLM_ELO_K or 24).
        prior      — initial rating (default 1500).
        since      — unix epoch lower bound (only votes after this).
        min_games  — drop models with fewer than this many games.
    """
    args = request.args

    def _f(name, default):
        v = args.get(name)
        if v is None or v == '':
            return default
        try:
            return float(v)
        except ValueError:
            return default

    lb = vote_arena.leaderboard(
        k=_f('k', vote_arena.DEFAULT_K),
        prior=_f('prior', vote_arena.DEFAULT_PRIOR),
        since=_f('since', None),
        min_games=int(_f('min_games', 0)),
    )
    return jsonify({'success': True, 'leaderboard': lb['ratings'], 'meta': lb['meta']})


@llm_bp.route('/arena/matrix', methods=['GET'])
def arena_matrix():
    """Head-to-head wins matrix for the top-N models."""
    try:
        top_n = int(request.args.get('top_n', 8))
    except ValueError:
        top_n = 8
    return jsonify({'success': True, 'matrix': vote_arena.pair_matrix(top_n=top_n)})


@llm_bp.route('/arena/agreement', methods=['GET'])
def arena_agreement():
    """Judge-vs-human agreement metric across all judged runs that received
    a decisive vote."""
    try:
        min_votes = int(request.args.get('min_votes', 1))
    except ValueError:
        min_votes = 1
    return jsonify({'success': True, 'agreement': vote_arena.agreement(min_votes=min_votes)})


@llm_bp.route('/arena/recent', methods=['GET'])
def arena_recent():
    """Recent votes feed."""
    try:
        limit = int(request.args.get('limit', 20))
    except ValueError:
        limit = 20
    return jsonify({'success': True, 'votes': vote_arena.recent_votes(limit=limit)})


@llm_bp.route('/arena/stats', methods=['GET'])
def arena_stats():
    """Top-of-page voting stats."""
    return jsonify({'success': True, 'stats': vote_arena.stats()})


# ---------------------------------------------------------------------------
# Prompt Library — versioned prompts linked back to Arena runs.
# Round-6 move (Day 28). A prompt has many versions; every version's runs
# accumulate in `runs.prompt_version_id`. Diff endpoint surfaces both text
# and score deltas so users see whether the revision actually helped.
# ---------------------------------------------------------------------------

@llm_bp.route('/prompts', methods=['GET'])
def prompts_list():
    """List prompts with version + run roll-ups (newest activity first)."""
    args = request.args

    def _bool(name: str) -> bool:
        v = args.get(name, '').strip().lower()
        return v in ('1', 'true', 'yes', 'on')

    rows, total = prompts_lib.list_prompts(
        q=(args.get('q') or '').strip() or None,
        starred_only=_bool('starred'),
        tag=(args.get('tag') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'prompts': rows, 'total': total})


@llm_bp.route('/prompts', methods=['POST'])
def prompts_create():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    prompt = prompts_lib.create_prompt(
        name=name,
        system_prompt=(data.get('system_prompt') or ''),
        user_template=(data.get('user_template') or ''),
        note=(data.get('note') or ''),
        tag=(data.get('tag') or '').strip() or None,
    )
    return jsonify({'success': True, 'prompt': prompt}), 201


@llm_bp.route('/prompts/stats', methods=['GET'])
def prompts_stats():
    return jsonify({'success': True, 'stats': prompts_lib.stats()})


@llm_bp.route('/prompts/diff', methods=['POST'])
def prompts_diff():
    data = request.get_json() or {}
    a = (data.get('a') or '').strip()
    b = (data.get('b') or '').strip()
    if not a or not b:
        return jsonify({'success': False, 'error': 'a and b are required'}), 400
    if a == b:
        return jsonify({'success': False, 'error': 'a and b must be different versions'}), 400
    result = prompts_lib.diff_versions(a, b)
    if result is None:
        return jsonify({'success': False, 'error': 'one or both versions not found'}), 404
    return jsonify({'success': True, 'diff': result})


@llm_bp.route('/prompts/<prompt_id>', methods=['GET'])
def prompts_get(prompt_id):
    p = prompts_lib.get_prompt(prompt_id)
    if not p:
        return jsonify({'success': False, 'error': 'prompt not found'}), 404
    return jsonify({'success': True, 'prompt': p})


@llm_bp.route('/prompts/<prompt_id>', methods=['DELETE'])
def prompts_delete(prompt_id):
    if not prompts_lib.delete_prompt(prompt_id):
        return jsonify({'success': False, 'error': 'prompt not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/prompts/<prompt_id>/meta', methods=['POST'])
def prompts_set_meta(prompt_id):
    data = request.get_json() or {}
    name = data.get('name')
    starred = data.get('starred')
    tag = data.get('tag')
    note = data.get('note')
    if name is None and starred is None and tag is None and note is None:
        return jsonify({'success': False, 'error': 'no updatable field'}), 400
    ok = prompts_lib.set_prompt_meta(
        prompt_id,
        name=name if isinstance(name, str) else None,
        starred=bool(starred) if starred is not None else None,
        tag=tag if isinstance(tag, str) else None,
        note=note if isinstance(note, str) else None,
    )
    if not ok:
        return jsonify({'success': False, 'error': 'prompt not found'}), 404
    return jsonify({'success': True, 'prompt': prompts_lib.get_prompt(prompt_id)})


@llm_bp.route('/prompts/<prompt_id>/versions', methods=['POST'])
def prompts_add_version(prompt_id):
    data = request.get_json() or {}
    v = prompts_lib.add_version(
        prompt_id,
        system_prompt=(data.get('system_prompt') or ''),
        user_template=(data.get('user_template') or ''),
        note=(data.get('note') or ''),
        parent_version_id=(data.get('parent_version_id') or '').strip() or None,
    )
    if v is None:
        return jsonify({'success': False, 'error': 'prompt not found'}), 404
    return jsonify({'success': True, 'version': v,
                    'prompt': prompts_lib.get_prompt(prompt_id)}), 201


@llm_bp.route('/prompts/<prompt_id>/versions/<version_id>/runs', methods=['GET'])
def prompts_version_runs(prompt_id, version_id):
    """Runs attached to a specific version. The ``prompt_id`` path slot is for
    URL hygiene only; the FK lives on the version row."""
    try:
        limit = int(request.args.get('limit', 50))
    except ValueError:
        limit = 50
    rows = prompts_lib.runs_for_version(version_id, limit=limit)
    return jsonify({'success': True, 'runs': rows, 'total': len(rows)})


# ---------------------------------------------------------------------------
# Eval Suites — reproducible test batteries. Define a fixed list of test
# cases, fan them out against any model, watch pass-rate + judge composite
# regress (or improve) as you change the prompt / swap the model. Round-8.
# ---------------------------------------------------------------------------

@llm_bp.route('/suites', methods=['GET'])
def suites_list():
    args = request.args

    def _bool(name: str) -> bool:
        v = args.get(name, '').strip().lower()
        return v in ('1', 'true', 'yes', 'on')

    rows, total = evals_lib.list_suites(
        q=(args.get('q') or '').strip() or None,
        tag=(args.get('tag') or '').strip() or None,
        starred_only=_bool('starred'),
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'suites': rows, 'total': total})


@llm_bp.route('/suites', methods=['POST'])
def suites_create():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    suite = evals_lib.create_suite(
        name=name,
        description=(data.get('description') or ''),
        tag=(data.get('tag') or '').strip() or None,
    )
    return jsonify({'success': True, 'suite': suite}), 201


@llm_bp.route('/suites/seed', methods=['POST'])
def suites_seed():
    """Idempotently create the 'Smoke Test' starter suite."""
    suite = evals_lib.seed_smoke_suite()
    return jsonify({'success': True, 'suite': suite}), 201


@llm_bp.route('/suites/stats', methods=['GET'])
def suites_stats():
    return jsonify({'success': True, 'stats': evals_lib.stats()})


@llm_bp.route('/suites/runs/compare', methods=['POST'])
def suites_runs_compare():
    data = request.get_json() or {}
    a = (data.get('a') or '').strip()
    b = (data.get('b') or '').strip()
    if not a or not b:
        return jsonify({'success': False, 'error': 'a and b are required'}), 400
    if a == b:
        return jsonify({'success': False, 'error': 'a and b must differ'}), 400
    result = evals_lib.compare_runs(a, b)
    if result is None:
        return jsonify({'success': False, 'error': 'one or both runs not found'}), 404
    return jsonify({'success': True, 'compare': result})


@llm_bp.route('/suites/runs/<run_id>', methods=['GET'])
def suites_run_get(run_id):
    run = evals_lib.get_run(run_id)
    if not run:
        return jsonify({'success': False, 'error': 'run not found'}), 404
    return jsonify({'success': True, 'run': run})


@llm_bp.route('/suites/runs/<run_id>', methods=['DELETE'])
def suites_run_delete(run_id):
    if not evals_lib.delete_run(run_id):
        return jsonify({'success': False, 'error': 'run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/suites/<suite_id>', methods=['GET'])
def suites_get(suite_id):
    suite = evals_lib.get_suite(suite_id)
    if not suite:
        return jsonify({'success': False, 'error': 'suite not found'}), 404
    return jsonify({'success': True, 'suite': suite})


@llm_bp.route('/suites/<suite_id>', methods=['DELETE'])
def suites_delete(suite_id):
    if not evals_lib.delete_suite(suite_id):
        return jsonify({'success': False, 'error': 'suite not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/suites/<suite_id>/meta', methods=['POST'])
def suites_set_meta(suite_id):
    data = request.get_json() or {}
    ok = evals_lib.set_suite_meta(
        suite_id,
        name=data.get('name') if isinstance(data.get('name'), str) else None,
        description=data.get('description') if isinstance(data.get('description'), str) else None,
        tag=data.get('tag') if isinstance(data.get('tag'), str) else None,
        starred=bool(data['starred']) if 'starred' in data else None,
    )
    if not ok:
        return jsonify({'success': False, 'error': 'suite not found or nothing to update'}), 404
    return jsonify({'success': True, 'suite': evals_lib.get_suite(suite_id)})


@llm_bp.route('/suites/<suite_id>/cases', methods=['POST'])
def suites_add_case(suite_id):
    data = request.get_json() or {}
    case = evals_lib.add_case(
        suite_id,
        title=data.get('title', ''),
        user_prompt=data.get('user_prompt', ''),
        expected_contains=data.get('expected_contains', ''),
        expected_not_contains=data.get('expected_not_contains', ''),
        expected_regex=data.get('expected_regex', ''),
        expect_json=bool(data.get('expect_json', False)),
        judge_min=data.get('judge_min'),
        note=data.get('note', ''),
    )
    if not case:
        return jsonify({'success': False, 'error': 'suite not found'}), 404
    return jsonify({'success': True, 'case': case,
                    'suite': evals_lib.get_suite(suite_id)}), 201


@llm_bp.route('/suites/<suite_id>/cases/<case_id>', methods=['POST'])
def suites_update_case(suite_id, case_id):
    data = request.get_json() or {}
    case = evals_lib.update_case(case_id, **data)
    if not case:
        return jsonify({'success': False, 'error': 'case not found'}), 404
    return jsonify({'success': True, 'case': case,
                    'suite': evals_lib.get_suite(suite_id)})


@llm_bp.route('/suites/<suite_id>/cases/<case_id>', methods=['DELETE'])
def suites_delete_case(suite_id, case_id):
    if not evals_lib.delete_case(case_id):
        return jsonify({'success': False, 'error': 'case not found'}), 404
    return jsonify({'success': True, 'suite': evals_lib.get_suite(suite_id)})


@llm_bp.route('/suites/<suite_id>/cases/reorder', methods=['POST'])
def suites_reorder_cases(suite_id):
    data = request.get_json() or {}
    ids = data.get('case_ids') or []
    if not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'case_ids must be a list'}), 400
    evals_lib.reorder_cases(suite_id, ids)
    return jsonify({'success': True, 'suite': evals_lib.get_suite(suite_id)})


@llm_bp.route('/suites/<suite_id>/runs', methods=['POST'])
def suites_run(suite_id):
    data = request.get_json() or {}
    provider = (data.get('provider') or '').strip()
    model = (data.get('model') or '').strip()
    if not provider or not model:
        return jsonify({'success': False, 'error': 'provider and model are required'}), 400
    try:
        run = evals_lib.run_suite(
            suite_id,
            provider=provider,
            model=model,
            system_prompt=(data.get('system_prompt') or ''),
            judge_provider=(data.get('judge_provider') or '').strip(),
            judge_model=(data.get('judge_model') or '').strip(),
            rubric=data.get('rubric'),
            note=(data.get('note') or ''),
            provider_factory=provider_factory,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    if run is None:
        return jsonify({'success': False, 'error': 'suite not found'}), 404
    if isinstance(run, dict) and run.get('error') == 'no cases in suite':
        return jsonify({'success': False, 'error': 'suite has no cases'}), 400
    return jsonify({'success': True, 'run': run})


@llm_bp.route('/suites/<suite_id>/runs', methods=['GET'])
def suites_runs_list(suite_id):
    rows, total = evals_lib.list_runs(
        suite_id=suite_id,
        limit=int(request.args.get('limit', 50) or 50),
        offset=int(request.args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'runs': rows, 'total': total})


# ---------------------------------------------------------------------------
# Rubrics Studio — first-class, versioned judge rubrics with per-dimension
# anchor-driven scoring. Round-9.
# ---------------------------------------------------------------------------

@llm_bp.route('/rubrics', methods=['GET'])
def rubrics_list():
    args = request.args

    def _bool(name: str) -> bool:
        v = args.get(name, '').strip().lower()
        return v in ('1', 'true', 'yes', 'on')

    rows, total = rubrics_lib.list_rubrics(
        q=(args.get('q') or '').strip() or None,
        tag=(args.get('tag') or '').strip() or None,
        starred_only=_bool('starred'),
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'rubrics': rows, 'total': total})


@llm_bp.route('/rubrics', methods=['POST'])
def rubrics_create():
    data = request.get_json() or {}
    try:
        rubric = rubrics_lib.create_rubric(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            tag=(data.get('tag') or '').strip(),
            dimensions=data.get('dimensions') or [],
            judge_addendum=(data.get('judge_addendum') or ''),
            note=(data.get('note') or ''),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'rubric': rubric}), 201


@llm_bp.route('/rubrics/seed', methods=['POST'])
def rubrics_seed():
    seeds = rubrics_lib.seed_rubrics()
    return jsonify({'success': True, 'rubrics': seeds}), 201


@llm_bp.route('/rubrics/stats', methods=['GET'])
def rubrics_stats():
    return jsonify({'success': True, 'stats': rubrics_lib.stats()})


@llm_bp.route('/rubrics/<rubric_id>', methods=['GET'])
def rubrics_get(rubric_id):
    rubric = rubrics_lib.get_rubric(rubric_id)
    if not rubric:
        return jsonify({'success': False, 'error': 'rubric not found'}), 404
    return jsonify({'success': True, 'rubric': rubric})


@llm_bp.route('/rubrics/<rubric_id>', methods=['DELETE'])
def rubrics_delete(rubric_id):
    if not rubrics_lib.delete_rubric(rubric_id):
        return jsonify({'success': False, 'error': 'rubric not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/rubrics/<rubric_id>/meta', methods=['POST'])
def rubrics_set_meta(rubric_id):
    data = request.get_json() or {}
    ok = rubrics_lib.set_rubric_meta(
        rubric_id,
        name=data.get('name') if isinstance(data.get('name'), str) else None,
        description=data.get('description') if isinstance(data.get('description'), str) else None,
        tag=data.get('tag') if isinstance(data.get('tag'), str) else None,
        starred=bool(data['starred']) if 'starred' in data else None,
    )
    if not ok:
        return jsonify({'success': False, 'error': 'rubric not found or nothing to update'}), 404
    return jsonify({'success': True, 'rubric': rubrics_lib.get_rubric(rubric_id)})


@llm_bp.route('/rubrics/<rubric_id>/revisions', methods=['POST'])
def rubrics_update(rubric_id):
    """Save a new revision iff dimensions / addendum changed."""
    data = request.get_json() or {}
    try:
        rubric = rubrics_lib.update_rubric(
            rubric_id,
            dimensions=data.get('dimensions') or [],
            judge_addendum=(data.get('judge_addendum') or ''),
            change_note=(data.get('note') or ''),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    if rubric is None:
        return jsonify({'success': False, 'error': 'rubric not found'}), 404
    return jsonify({'success': True, 'rubric': rubric})


@llm_bp.route('/rubrics/<rubric_id>/revisions/<int:revision_num>/restore', methods=['POST'])
def rubrics_restore(rubric_id, revision_num):
    data = request.get_json() or {}
    rubric = rubrics_lib.restore_revision(
        rubric_id, int(revision_num),
        note=(data.get('note') or ''),
    )
    if rubric is None:
        return jsonify({'success': False, 'error': 'rubric or revision not found'}), 404
    return jsonify({'success': True, 'rubric': rubric})


@llm_bp.route('/rubrics/<rubric_id>/test', methods=['POST'])
def rubrics_test(rubric_id):
    """Run the rubric judging engine against an ad-hoc (prompt, response) pair.

    The response is whatever the user pasted — a real model output, a candidate
    from Arena, anything. Persisted so the judgement log + stats stay live.
    """
    data = request.get_json() or {}
    user_prompt = (data.get('user_prompt') or '').strip()
    response = (data.get('response') or '').strip()
    judge_provider = (data.get('judge_provider') or '').strip()
    judge_model = (data.get('judge_model') or '').strip()
    if not user_prompt:
        return jsonify({'success': False, 'error': 'user_prompt is required'}), 400
    if not response:
        return jsonify({'success': False, 'error': 'response is required'}), 400
    if not judge_provider or not judge_model:
        return jsonify({'success': False, 'error': 'judge_provider and judge_model are required'}), 400

    try:
        payload, status = rubrics_lib.judge_with_rubric(
            rubric_id,
            user_prompt=user_prompt,
            response=response,
            judge_provider=judge_provider,
            judge_model=judge_model,
            system_prompt=(data.get('system_prompt') or ''),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            note=(data.get('note') or ''),
            provider_factory=provider_factory,
            persist=bool(data.get('persist', True)),
            revision_num=data.get('revision_num'),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


@llm_bp.route('/rubrics/<rubric_id>/judgements', methods=['GET'])
def rubrics_judgements_list(rubric_id):
    rows, total = rubrics_lib.list_judgements(
        rubric_id,
        limit=int(request.args.get('limit', 50) or 50),
        offset=int(request.args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'judgements': rows, 'total': total})


@llm_bp.route('/rubrics/judgements/<judgement_id>', methods=['DELETE'])
def rubrics_judgement_delete(judgement_id):
    if not rubrics_lib.delete_judgement(judgement_id):
        return jsonify({'success': False, 'error': 'judgement not found'}), 404
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Optimizer Studio — automated prompt evolution against a rubric. Round-10.
# ---------------------------------------------------------------------------

@llm_bp.route('/optimize/mutations', methods=['GET'])
def optimize_mutations():
    return jsonify({'success': True, 'mutations': optimizer_lib.mutation_catalog()})


@llm_bp.route('/optimize/preview', methods=['POST'])
def optimize_preview():
    """Dry-render every mutation against ``base_prompt`` so the Setup pane
    shows the user what each strategy would do before committing to a run."""
    data = request.get_json() or {}
    base_prompt = (data.get('base_prompt') or '').strip()
    if not base_prompt:
        return jsonify({'success': False, 'error': 'base_prompt is required'}), 400
    cases = data.get('test_cases') or []
    rubric_id = (data.get('rubric_id') or '').strip()
    rubric_dims = []
    if rubric_id:
        rb = rubrics_lib.get_rubric(rubric_id, include_revisions=False, recent_judgements=0)
        if rb:
            rubric_dims = rb.get('dimensions') or []
    out = optimizer_lib.preview_all_mutations(base_prompt, {
        'cases': cases,
        'rubric_dimensions': rubric_dims,
    })
    return jsonify({'success': True, 'previews': out})


@llm_bp.route('/optimize', methods=['GET'])
def optimize_list():
    args = request.args
    rows, total = optimizer_lib.list_optimizations(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'optimizations': rows, 'total': total})


@llm_bp.route('/optimize', methods=['POST'])
def optimize_create():
    data = request.get_json() or {}
    try:
        opt = optimizer_lib.create_optimization(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            base_prompt=(data.get('base_prompt') or '').strip(),
            rubric_id=(data.get('rubric_id') or '').strip(),
            rubric_revision=data.get('rubric_revision'),
            judge_provider=(data.get('judge_provider') or '').strip(),
            judge_model=(data.get('judge_model') or '').strip(),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            test_cases=data.get('test_cases') or [],
            target_generations=int(data.get('target_generations') or 3),
            strategy=data.get('strategy'),
            dryrun=bool(data.get('dryrun', False)),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'optimization': opt}), 201


@llm_bp.route('/optimize/seed', methods=['POST'])
def optimize_seed():
    opt = optimizer_lib.seed_demo()
    return jsonify({'success': True, 'optimization': opt}), 201


@llm_bp.route('/optimize/stats', methods=['GET'])
def optimize_stats():
    return jsonify({'success': True, 'stats': optimizer_lib.stats()})


@llm_bp.route('/optimize/<opt_id>', methods=['GET'])
def optimize_get(opt_id):
    opt = optimizer_lib.get_optimization(opt_id)
    if not opt:
        return jsonify({'success': False, 'error': 'optimization not found'}), 404
    return jsonify({'success': True, 'optimization': opt})


@llm_bp.route('/optimize/<opt_id>', methods=['DELETE'])
def optimize_delete(opt_id):
    if not optimizer_lib.delete_optimization(opt_id):
        return jsonify({'success': False, 'error': 'optimization not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/optimize/<opt_id>/advance', methods=['POST'])
def optimize_advance(opt_id):
    """Run one generation. The frontend can call this repeatedly to step
    through evolution, or hit ``/run`` to consume all remaining generations
    in one shot (for dry-run only — live mode should be stepped)."""
    try:
        payload, status = optimizer_lib.advance_generation(
            opt_id, provider_factory=provider_factory,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


@llm_bp.route('/optimize/<opt_id>/run', methods=['POST'])
def optimize_run_all(opt_id):
    """Consume every remaining generation in one call. Intended for the demo /
    dry-run path; live runs should step generation-by-generation so the user
    can stop after each one if they don't like where it's going."""
    opt = optimizer_lib.get_optimization(opt_id)
    if not opt:
        return jsonify({'success': False, 'error': 'optimization not found'}), 404
    if not opt['dryrun']:
        # Refuse to spend money in one shot without explicit confirmation.
        data = request.get_json() or {}
        if not data.get('confirm_live'):
            return jsonify({
                'success': False,
                'error': "live optimization: pass {confirm_live: true} or step via /advance",
            }), 400
    remaining = opt['target_generations'] - opt['generations_done']
    if remaining <= 0:
        return jsonify({'success': False, 'error': 'no generations remaining'}), 400
    gens_run = []
    for _ in range(remaining):
        try:
            payload, status = optimizer_lib.advance_generation(
                opt_id, provider_factory=provider_factory,
            )
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(exc)}), 500
        if status != 200:
            return jsonify(payload), status
        gens_run.append({
            'generation': payload['generation'],
            'best': payload.get('best_in_generation'),
            'cost': payload.get('gen_cost'),
        })
    return jsonify({
        'success': True,
        'optimization': optimizer_lib.get_optimization(opt_id),
        'generations_run': gens_run,
    })


@llm_bp.route('/optimize/<opt_id>/promote/<variant_id>', methods=['POST'])
def optimize_promote(opt_id, variant_id):
    opt = optimizer_lib.promote_variant(opt_id, variant_id)
    if opt is None:
        return jsonify({'success': False, 'error': 'optimization or variant not found'}), 404
    return jsonify({'success': True, 'optimization': opt})


# ---------------------------------------------------------------------------
# Adversary Lab — prompt robustness tester. Day-53.
# ---------------------------------------------------------------------------

@llm_bp.route('/adversary/perturbations', methods=['GET'])
def adversary_perturbations():
    return jsonify({'success': True, 'perturbations': adversary_lib.perturbation_catalog()})


@llm_bp.route('/adversary/preview', methods=['POST'])
def adversary_preview():
    """Dry-render every perturbation against a base prompt + optional sample
    input. Drives the Setup-tab live preview without persisting anything."""
    data = request.get_json() or {}
    base_prompt = (data.get('base_prompt') or '').strip()
    if not base_prompt:
        return jsonify({'success': False, 'error': 'base_prompt is required'}), 400
    sample_input = (data.get('sample_input') or '').strip()
    kinds = data.get('kinds') if isinstance(data.get('kinds'), list) else None
    out = adversary_lib.preview_perturbations(base_prompt, sample_input, kinds)
    return jsonify({'success': True, 'previews': out})


@llm_bp.route('/adversary', methods=['GET'])
def adversary_list():
    args = request.args
    rows, total = adversary_lib.list_audits(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'audits': rows, 'total': total})


@llm_bp.route('/adversary', methods=['POST'])
def adversary_create():
    data = request.get_json() or {}
    try:
        audit = adversary_lib.create_audit(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            base_prompt=(data.get('base_prompt') or '').strip(),
            rubric_id=(data.get('rubric_id') or '').strip(),
            rubric_revision=data.get('rubric_revision'),
            judge_provider=(data.get('judge_provider') or '').strip(),
            judge_model=(data.get('judge_model') or '').strip(),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            test_cases=data.get('test_cases') or [],
            perturbations=data.get('perturbations'),
            dryrun=bool(data.get('dryrun', False)),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'audit': audit}), 201


@llm_bp.route('/adversary/seed', methods=['POST'])
def adversary_seed():
    audit = adversary_lib.seed_demo()
    return jsonify({'success': True, 'audit': audit}), 201


@llm_bp.route('/adversary/stats', methods=['GET'])
def adversary_stats():
    return jsonify({'success': True, 'stats': adversary_lib.stats()})


@llm_bp.route('/adversary/<audit_id>', methods=['GET'])
def adversary_get(audit_id):
    audit = adversary_lib.get_audit(audit_id)
    if not audit:
        return jsonify({'success': False, 'error': 'audit not found'}), 404
    return jsonify({'success': True, 'audit': audit})


@llm_bp.route('/adversary/<audit_id>', methods=['DELETE'])
def adversary_delete(audit_id):
    if not adversary_lib.delete_audit(audit_id):
        return jsonify({'success': False, 'error': 'audit not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/adversary/<audit_id>/run', methods=['POST'])
def adversary_run(audit_id):
    """Run the audit — clean baseline + every selected perturbation.

    For live mode requires ``{confirm_live: true}`` so we don't accidentally
    spend money. Dry-run mode runs instantly and needs no keys."""
    data = request.get_json() or {}
    try:
        payload, status = adversary_lib.run_audit(
            audit_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


# ─── Showdown Arena ────────────────────────────────────────────────────────
# Paired A/B testing of two prompts ("Champion" vs "Challenger") across a
# shared set of test cases. Surfaces real statistics — mean Δ, paired
# bootstrap 95% CI, sign-test p-value, Cohen's d, win rate — and a
# ship/keep/no-decision verdict. Round-13.

@llm_bp.route('/showdown', methods=['GET'])
def showdown_list():
    args = request.args
    rows, total = showdown_lib.list_showdowns(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        decision=(args.get('decision') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'showdowns': rows, 'total': total})


@llm_bp.route('/showdown', methods=['POST'])
def showdown_create():
    data = request.get_json() or {}
    try:
        sd = showdown_lib.create_showdown(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            champion_prompt=(data.get('champion_prompt') or '').strip(),
            challenger_prompt=(data.get('challenger_prompt') or '').strip(),
            champion_label=(data.get('champion_label') or 'Champion'),
            challenger_label=(data.get('challenger_label') or 'Challenger'),
            rubric_id=(data.get('rubric_id') or '').strip(),
            rubric_revision=data.get('rubric_revision'),
            judge_provider=(data.get('judge_provider') or '').strip(),
            judge_model=(data.get('judge_model') or '').strip(),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            test_cases=data.get('test_cases') or [],
            dryrun=bool(data.get('dryrun', False)),
            n_bootstrap=data.get('n_bootstrap', showdown_lib.DEFAULT_BOOTSTRAP),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'showdown': sd}), 201


@llm_bp.route('/showdown/seed', methods=['POST'])
def showdown_seed():
    sd = showdown_lib.seed_demo()
    return jsonify({'success': True, 'showdown': sd}), 201


@llm_bp.route('/showdown/stats', methods=['GET'])
def showdown_stats():
    return jsonify({'success': True, 'stats': showdown_lib.stats()})


@llm_bp.route('/showdown/<showdown_id>', methods=['GET'])
def showdown_get(showdown_id):
    sd = showdown_lib.get_showdown(showdown_id)
    if not sd:
        return jsonify({'success': False, 'error': 'showdown not found'}), 404
    return jsonify({'success': True, 'showdown': sd})


@llm_bp.route('/showdown/<showdown_id>', methods=['DELETE'])
def showdown_delete(showdown_id):
    if not showdown_lib.delete_showdown(showdown_id):
        return jsonify({'success': False, 'error': 'showdown not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/showdown/<showdown_id>/run', methods=['POST'])
def showdown_run(showdown_id):
    """Run the showdown — both prompts × every case, paired stats roll-up."""
    data = request.get_json() or {}
    try:
        payload, status = showdown_lib.run_showdown(
            showdown_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


@llm_bp.route('/insights', methods=['GET'])
def studio_insights():
    """Cross-cutting analytics over the whole run history: model scorecards,
    the quality/cost efficiency frontier, spend timeline, provider roll-up, and
    a headline summary — all derived from the persisted runs + ELO votes."""
    try:
        min_appearances = int(request.args.get('min_appearances', 1) or 1)
    except (TypeError, ValueError):
        min_appearances = 1
    data = insights_lib.build_insights(min_appearances=max(1, min_appearances))
    return jsonify({'success': True, **data})


# ─── Drift Lab ─────────────────────────────────────────────────────────────
# Output-stability tester. Replays the exact same prompt against the exact
# same model N times and rolls the bag into a composite Stability Score +
# pairwise similarity matrix + cluster summary + variance-type verdict.
# Answers the question every "temperature > 0" prompt eventually asks:
# *how non-deterministic is this thing in production?* Round-14.

@llm_bp.route('/drift/defaults', methods=['GET'])
def drift_defaults():
    return jsonify({'success': True, 'defaults': drift_lib.defaults()})


@llm_bp.route('/drift/stats', methods=['GET'])
def drift_stats():
    return jsonify({'success': True, 'stats': drift_lib.stats()})


@llm_bp.route('/drift', methods=['GET'])
def drift_list():
    args = request.args
    rows, total = drift_lib.list_drifts(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'drifts': rows, 'total': total})


@llm_bp.route('/drift', methods=['POST'])
def drift_create():
    data = request.get_json() or {}
    try:
        drift = drift_lib.create_drift(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            system_prompt=(data.get('system_prompt') or ''),
            user_prompt=(data.get('user_prompt') or '').strip(),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            temperature=data.get('temperature', drift_lib.DEFAULT_TEMPERATURE),
            top_p=data.get('top_p', drift_lib.DEFAULT_TOP_P),
            n_replays=data.get('n_replays', drift_lib.DEFAULT_N_REPLAYS),
            cluster_threshold=data.get('cluster_threshold', drift_lib.DEFAULT_CLUSTER_THRESHOLD),
            dryrun=bool(data.get('dryrun', False)),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'drift': drift}), 201


@llm_bp.route('/drift/seed', methods=['POST'])
def drift_seed():
    drift = drift_lib.seed_demo()
    return jsonify({'success': True, 'drift': drift}), 201


@llm_bp.route('/drift/<drift_id>', methods=['GET'])
def drift_get(drift_id):
    drift = drift_lib.get_drift(drift_id)
    if not drift:
        return jsonify({'success': False, 'error': 'drift run not found'}), 404
    return jsonify({'success': True, 'drift': drift})


@llm_bp.route('/drift/<drift_id>', methods=['DELETE'])
def drift_delete(drift_id):
    if not drift_lib.delete_drift(drift_id):
        return jsonify({'success': False, 'error': 'drift run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/drift/<drift_id>/run', methods=['POST'])
def drift_run(drift_id):
    """Execute the replay batch and roll the bag into stability metrics.

    Live mode requires ``{confirm_live: true}`` so we don't accidentally
    spend API credits."""
    data = request.get_json() or {}
    try:
        payload, status = drift_lib.run_drift(
            drift_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# Prompt Surgeon — section-level ablation & attribution. Round-15.
# Tells you which paragraphs of your prompt are load-bearing and which are
# dead weight you can cut for $$$ off every call.
# ---------------------------------------------------------------------------

@llm_bp.route('/surgeon/defaults', methods=['GET'])
def surgeon_defaults():
    return jsonify({'success': True, 'defaults': surgeon_lib.defaults()})


@llm_bp.route('/surgeon/stats', methods=['GET'])
def surgeon_stats():
    return jsonify({'success': True, 'stats': surgeon_lib.stats()})


@llm_bp.route('/surgeon/parse', methods=['POST'])
def surgeon_parse():
    """Stateless section preview — used by the editor to render the
    section grid before the user commits to a run."""
    data = request.get_json() or {}
    sections = surgeon_lib.parse_sections(data.get('system_prompt') or '')
    return jsonify({'success': True, 'sections': sections, 'total_tokens': sum(s['tokens'] for s in sections)})


@llm_bp.route('/surgeon', methods=['GET'])
def surgeon_list():
    args = request.args
    rows, total = surgeon_lib.list_surgeons(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'surgeons': rows, 'total': total})


@llm_bp.route('/surgeon', methods=['POST'])
def surgeon_create():
    data = request.get_json() or {}
    try:
        surg = surgeon_lib.create_surgeon(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            system_prompt=(data.get('system_prompt') or ''),
            user_prompt=(data.get('user_prompt') or '').strip(),
            candidate_provider=(data.get('candidate_provider') or '').strip(),
            candidate_model=(data.get('candidate_model') or '').strip(),
            temperature=data.get('temperature', surgeon_lib.DEFAULT_TEMPERATURE),
            top_p=data.get('top_p', surgeon_lib.DEFAULT_TOP_P),
            n_replays=data.get('n_replays', surgeon_lib.DEFAULT_N_REPLAYS),
            monthly_calls=data.get('monthly_calls', surgeon_lib.DEFAULT_MONTHLY_CALLS),
            dryrun=bool(data.get('dryrun', False)),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'surgeon': surg}), 201


@llm_bp.route('/surgeon/seed', methods=['POST'])
def surgeon_seed():
    surg = surgeon_lib.seed_demo()
    return jsonify({'success': True, 'surgeon': surg}), 201


@llm_bp.route('/surgeon/<surgeon_id>', methods=['GET'])
def surgeon_get(surgeon_id):
    surg = surgeon_lib.get_surgeon(surgeon_id)
    if not surg:
        return jsonify({'success': False, 'error': 'surgeon run not found'}), 404
    return jsonify({'success': True, 'surgeon': surg})


@llm_bp.route('/surgeon/<surgeon_id>', methods=['DELETE'])
def surgeon_delete(surgeon_id):
    if not surgeon_lib.delete_surgeon(surgeon_id):
        return jsonify({'success': False, 'error': 'surgeon run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/surgeon/<surgeon_id>/run', methods=['POST'])
def surgeon_run(surgeon_id):
    """Execute the ablation sweep. Live mode requires
    ``{confirm_live: true}`` so we never silently spend API credits."""
    data = request.get_json() or {}
    try:
        payload, status = surgeon_lib.run_surgeon(
            surgeon_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# Frontier — Cost/Quality Pareto Explorer. Round-16.
# For a prompt + candidate model roster, computes each model's quality vs
# cost, filters to the Pareto frontier, kneedles the elbow, and hands back
# three shippable recommendations (default / cheapest-at-quality-floor /
# best-within-budget) plus the monthly $ savings each implies.
# ---------------------------------------------------------------------------

@llm_bp.route('/frontier/defaults', methods=['GET'])
def frontier_defaults():
    return jsonify({'success': True, 'defaults': frontier_lib.defaults()})


@llm_bp.route('/frontier/stats', methods=['GET'])
def frontier_stats():
    return jsonify({'success': True, 'stats': frontier_lib.stats()})


@llm_bp.route('/frontier', methods=['GET'])
def frontier_list():
    args = request.args
    rows, total = frontier_lib.list_frontiers(
        q=(args.get('q') or '').strip() or None,
        status=(args.get('status') or '').strip() or None,
        limit=int(args.get('limit', 100) or 100),
        offset=int(args.get('offset', 0) or 0),
    )
    return jsonify({'success': True, 'frontiers': rows, 'total': total})


@llm_bp.route('/frontier', methods=['POST'])
def frontier_create():
    data = request.get_json() or {}
    try:
        run = frontier_lib.create_frontier(
            name=(data.get('name') or '').strip(),
            description=(data.get('description') or ''),
            system_prompt=(data.get('system_prompt') or ''),
            user_prompt=(data.get('user_prompt') or '').strip(),
            temperature=data.get('temperature', frontier_lib.DEFAULT_TEMPERATURE),
            top_p=data.get('top_p', frontier_lib.DEFAULT_TOP_P),
            n_replays=data.get('n_replays', frontier_lib.DEFAULT_N_REPLAYS),
            monthly_calls=data.get('monthly_calls', frontier_lib.DEFAULT_MONTHLY_CALLS),
            quality_floor=data.get('quality_floor'),
            budget_ceiling=data.get('budget_ceiling'),
            dryrun=bool(data.get('dryrun', False)),
            roster=data.get('roster') or None,
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'frontier': run}), 201


@llm_bp.route('/frontier/seed', methods=['POST'])
def frontier_seed():
    run = frontier_lib.seed_demo()
    return jsonify({'success': True, 'frontier': run}), 201


@llm_bp.route('/frontier/<frontier_id>', methods=['GET'])
def frontier_get(frontier_id):
    run = frontier_lib.get_frontier(frontier_id)
    if not run:
        return jsonify({'success': False, 'error': 'frontier run not found'}), 404
    return jsonify({'success': True, 'frontier': run})


@llm_bp.route('/frontier/<frontier_id>', methods=['DELETE'])
def frontier_delete(frontier_id):
    if not frontier_lib.delete_frontier(frontier_id):
        return jsonify({'success': False, 'error': 'frontier run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/frontier/<frontier_id>/run', methods=['POST'])
def frontier_run(frontier_id):
    """Execute the roster sweep. Live mode requires ``{confirm_live: true}``
    so we never silently spend API credits."""
    data = request.get_json() or {}
    try:
        payload, status = frontier_lib.run_frontier(
            frontier_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


@llm_bp.route('/frontier/<frontier_id>/recommend', methods=['POST'])
def frontier_recommend(frontier_id):
    """Re-derive picks from persisted points against fresh constraints —
    lets the UI slider (min-quality / max-cost) update the recommendation
    live without re-firing the whole roster sweep."""
    run = frontier_lib.get_frontier(frontier_id)
    if not run:
        return jsonify({'success': False, 'error': 'frontier run not found'}), 404
    data = request.get_json() or {}
    points = run.get('points') or []
    valid = [p for p in points if p.get('quality') is not None and p.get('cost_per_call') is not None]
    if not valid:
        return jsonify({'success': True, 'quality_pick': None, 'budget_pick': None}), 200
    top = max(valid, key=lambda x: (x['quality'], -x['cost_per_call']))
    monthly_calls = int(data.get('monthly_calls') or run.get('monthly_calls') or 50000)

    def _rec(pt):
        if not pt:
            return None
        s = max(0.0, (top['cost_per_call'] or 0) - (pt['cost_per_call'] or 0)) * monthly_calls
        kept = round(100.0 * (pt['quality'] or 0) / (top['quality'] or 1), 1)
        return {
            'provider': pt['provider'], 'model': pt['model'],
            'key': f"{pt['provider']}:{pt['model']}",
            'tier': pt.get('tier'),
            'quality': pt.get('quality'),
            'cost_per_call': pt.get('cost_per_call'),
            'monthly_cost': round((pt.get('cost_per_call') or 0) * monthly_calls, 2),
            'monthly_savings': round(s, 2),
            'quality_kept_pct': kept,
        }

    quality_floor = data.get('quality_floor')
    budget_ceiling = data.get('budget_ceiling')
    q_pick = None
    b_pick = None
    if quality_floor is not None:
        eligible = [p for p in valid if p['quality'] >= float(quality_floor)]
        q_pick = min(eligible, key=lambda x: (x['cost_per_call'], -x['quality'])) if eligible else None
    if budget_ceiling is not None:
        eligible = [p for p in valid if p['cost_per_call'] <= float(budget_ceiling)]
        b_pick = max(eligible, key=lambda x: (x['quality'], -x['cost_per_call'])) if eligible else None
    return jsonify({
        'success': True,
        'top_quality': _rec(top),
        'quality_pick': _rec(q_pick),
        'budget_pick': _rec(b_pick),
    }), 200


# ---------------------------------------------------------------------------
# Relay — Cascade Router Designer.
# ---------------------------------------------------------------------------

@llm_bp.route('/relay/defaults', methods=['GET'])
def relay_defaults():
    return jsonify({'success': True, 'defaults': relay_lib.defaults()})


@llm_bp.route('/relay/stats', methods=['GET'])
def relay_stats():
    return jsonify({'success': True, 'stats': relay_lib.stats()})


@llm_bp.route('/relay', methods=['GET'])
def relay_list():
    args = request.args
    rows, total = relay_lib.list_relays(
        q=args.get('q') or None,
        status=args.get('status') or None,
        limit=int(args.get('limit', 100)),
        offset=int(args.get('offset', 0)),
    )
    return jsonify({'success': True, 'relays': rows, 'total': total})


@llm_bp.route('/relay', methods=['POST'])
def relay_create():
    data = request.get_json() or {}
    try:
        run = relay_lib.create_relay(
            name=str(data.get('name') or 'Relay run'),
            description=str(data.get('description') or ''),
            system_prompt=str(data.get('system_prompt') or ''),
            user_prompt=str(data.get('user_prompt') or ''),
            temperature=data.get('temperature', relay_lib.DEFAULT_TEMPERATURE),
            top_p=data.get('top_p', relay_lib.DEFAULT_TOP_P),
            n_replays=data.get('n_replays', relay_lib.DEFAULT_N_REPLAYS),
            monthly_calls=data.get('monthly_calls', relay_lib.DEFAULT_MONTHLY_CALLS),
            gate_type=str(data.get('gate_type') or relay_lib.DEFAULT_GATE_TYPE),
            gate_threshold=data.get('gate_threshold'),
            quality_floor=data.get('quality_floor'),
            latency_ceiling_ms=data.get('latency_ceiling_ms'),
            dryrun=bool(data.get('dryrun', True)),
            roster=data.get('roster'),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'relay': run}), 201


@llm_bp.route('/relay/seed', methods=['POST'])
def relay_seed():
    run = relay_lib.seed_demo()
    return jsonify({'success': True, 'relay': run}), 201


@llm_bp.route('/relay/<relay_id>', methods=['GET'])
def relay_get(relay_id):
    run = relay_lib.get_relay(relay_id)
    if not run:
        return jsonify({'success': False, 'error': 'relay run not found'}), 404
    return jsonify({'success': True, 'relay': run})


@llm_bp.route('/relay/<relay_id>', methods=['DELETE'])
def relay_delete(relay_id):
    if not relay_lib.delete_relay(relay_id):
        return jsonify({'success': False, 'error': 'relay run not found'}), 404
    return jsonify({'success': True})


@llm_bp.route('/relay/<relay_id>/run', methods=['POST'])
def relay_run(relay_id):
    data = request.get_json() or {}
    try:
        payload, status = relay_lib.run_relay(
            relay_id,
            provider_factory=provider_factory,
            confirm_live=bool(data.get('confirm_live', False)),
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify(payload), status


@llm_bp.route('/relay/<relay_id>/preview', methods=['POST'])
def relay_preview(relay_id):
    """Re-simulate a persisted relay under a new gate / picked-subset /
    constraint set — no new calls, just re-derives from stored replays.
    Powers the live gate-threshold slider and the level-toggle."""
    data = request.get_json() or {}
    picked = data.get('picked_indexes')
    if picked is not None:
        try:
            picked = [int(x) for x in picked]
        except (TypeError, ValueError):
            picked = None
    result = relay_lib.preview_gate(
        relay_id,
        gate_type=data.get('gate_type'),
        gate_threshold=data.get('gate_threshold'),
        quality_floor=data.get('quality_floor'),
        latency_ceiling_ms=data.get('latency_ceiling_ms'),
        picked_indexes=picked,
        monthly_calls=data.get('monthly_calls'),
    )
    if result is None:
        return jsonify({'success': False, 'error': 'relay run not found'}), 404
    return jsonify({'success': True, 'preview': result}), 200


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


# ─── Studio Sentinel — Prompt-Injection Defense (Day 83) ───────────────────
# Deterministic engine. Every response is a pure function of the request
# body, no persistence, so the studio lights up on first page load without
# any API credentials and stays byte-identical across refreshes.

@llm_bp.route('/sentinel/defaults', methods=['GET'])
def sentinel_defaults():
    return jsonify({'success': True, 'defaults': sentinel_lib.defaults()})


@llm_bp.route('/sentinel/attacks', methods=['GET'])
def sentinel_attacks():
    return jsonify({
        'success': True,
        'attacks': sentinel_lib.list_attacks(),
        'families': sentinel_lib.list_families(),
    })


@llm_bp.route('/sentinel/defenses', methods=['GET'])
def sentinel_defenses():
    return jsonify({'success': True, 'defenses': sentinel_lib.list_defenses()})


@llm_bp.route('/sentinel/scan', methods=['POST'])
def sentinel_scan():
    try:
        data = request.get_json(silent=True) or {}
        text = str(data.get('input') or data.get('text') or '')
        if not text.strip():
            return jsonify({'success': False, 'error': 'input is required'}), 400
        return jsonify({'success': True, 'scan': sentinel_lib.scan_input(text)})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sentinel/matrix', methods=['POST'])
def sentinel_matrix():
    try:
        data = request.get_json(silent=True) or {}
        defense_ids = data.get('defense_ids')
        if defense_ids is not None and not isinstance(defense_ids, list):
            return jsonify({'success': False, 'error': 'defense_ids must be a list'}), 400
        matrix = sentinel_lib.build_matrix(defense_ids)
        return jsonify({'success': True, 'matrix': matrix})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sentinel/simulate', methods=['POST'])
def sentinel_simulate():
    try:
        data = request.get_json(silent=True) or {}
        defense_ids = data.get('defense_ids') or []
        if not isinstance(defense_ids, list):
            return jsonify({'success': False, 'error': 'defense_ids must be a list'}), 400
        traffic_attack_pct = float(data.get('traffic_attack_pct', sentinel_lib.DEFAULT_TRAFFIC_ATTACK_PCT))
        monthly_requests = int(data.get('monthly_requests', sentinel_lib.DEFAULT_MONTHLY_REQUESTS))
        attack_mix = data.get('attack_mix')
        sim = sentinel_lib.simulate_policy(
            defense_ids,
            traffic_attack_pct=max(0.0, min(1.0, traffic_attack_pct)),
            monthly_requests=max(1, monthly_requests),
            attack_mix=attack_mix if isinstance(attack_mix, dict) else None,
        )
        return jsonify({'success': True, 'simulation': sim})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sentinel/suggest', methods=['POST'])
def sentinel_suggest():
    try:
        data = request.get_json(silent=True) or {}
        picks = sentinel_lib.suggest_policies(
            traffic_attack_pct=max(0.0, min(1.0, float(data.get(
                'traffic_attack_pct', sentinel_lib.DEFAULT_TRAFFIC_ATTACK_PCT
            )))),
            monthly_requests=max(1, int(data.get(
                'monthly_requests', sentinel_lib.DEFAULT_MONTHLY_REQUESTS
            ))),
            fpr_ceiling=max(0.0, min(1.0, float(data.get(
                'fpr_ceiling', sentinel_lib.DEFAULT_FPR_CEILING
            )))),
            latency_ceiling_ms=max(0, int(data.get(
                'latency_ceiling_ms', sentinel_lib.DEFAULT_LATENCY_CEILING_MS
            ))),
        )
        return jsonify({'success': True, 'picks': picks})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sentinel/compile', methods=['POST'])
def sentinel_compile():
    try:
        data = request.get_json(silent=True) or {}
        defense_ids = data.get('defense_ids') or []
        if not isinstance(defense_ids, list) or not defense_ids:
            return jsonify({'success': False, 'error': 'defense_ids must be a non-empty list'}), 400
        risk_threshold = int(data.get('risk_threshold', sentinel_lib.DEFAULT_RISK_THRESHOLD))
        action_on_block = str(data.get('action_on_block') or 'refuse')
        policy = sentinel_lib.compile_policy(
            defense_ids,
            risk_threshold=max(0, min(100, risk_threshold)),
            action_on_block=action_on_block,
            traffic_attack_pct=max(0.0, min(1.0, float(data.get(
                'traffic_attack_pct', sentinel_lib.DEFAULT_TRAFFIC_ATTACK_PCT
            )))),
            monthly_requests=max(1, int(data.get(
                'monthly_requests', sentinel_lib.DEFAULT_MONTHLY_REQUESTS
            ))),
        )
        markdown = sentinel_lib.policy_markdown(policy)
        return jsonify({'success': True, 'policy': policy, 'markdown': markdown})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sentinel/seed', methods=['GET', 'POST'])
def sentinel_seed():
    try:
        return jsonify({'success': True, 'seed': sentinel_lib.seed_demo()})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Studio Cache — Semantic Response Cache (Day 88) ───────────────────────
# Deterministic engine. No persistence, no keys required — every response is a
# pure function of the workload and config, so the studio lights up on first
# page load and stays byte-identical across refreshes.


def _cache_resolve_workload(data):
    """Load workload by ``workload_id`` or take an inline ``workload`` list.

    If the caller passes ``workload`` explicitly, we honour their intent even
    if it's empty (raise) — that beats silently substituting a demo workload
    when the caller thought they were exercising their own.
    """
    if 'workload' in data:
        inline = data.get('workload')
        if not isinstance(inline, list):
            raise ValueError('workload must be a list of prompts')
        cleaned = []
        for item in inline:
            if isinstance(item, str):
                cleaned.append({'prompt': item})
            elif isinstance(item, dict) and item.get('prompt'):
                cleaned.append({
                    'prompt': str(item.get('prompt')),
                    'intent': str(item.get('intent') or ''),
                    'timestamp': int(item.get('timestamp', len(cleaned))),
                })
        if not cleaned:
            raise ValueError('workload is empty')
        return cleaned
    workload_id = str(data.get('workload_id') or 'customer_support')
    return cache_lib.load_workload(workload_id)


@llm_bp.route('/cache/defaults', methods=['GET'])
def cache_defaults():
    return jsonify({'success': True, 'defaults': cache_lib.defaults()})


@llm_bp.route('/cache/policies', methods=['GET'])
def cache_policies():
    return jsonify({'success': True, 'policies': cache_lib.list_policies()})


@llm_bp.route('/cache/workloads', methods=['GET'])
def cache_workloads():
    return jsonify({'success': True, 'workloads': cache_lib.list_workloads()})


@llm_bp.route('/cache/simulate', methods=['POST'])
def cache_simulate():
    try:
        data = request.get_json(silent=True) or {}
        workload = _cache_resolve_workload(data)
        if not workload:
            return jsonify({'success': False, 'error': 'workload is empty'}), 400
        sim = cache_lib.simulate_cache(
            workload,
            threshold=float(data.get('threshold', cache_lib.DEFAULT_THRESHOLD)),
            capacity=int(data.get('capacity', cache_lib.DEFAULT_CAPACITY)),
            ttl_seconds=int(data.get('ttl_seconds', cache_lib.DEFAULT_TTL_SECONDS)),
            policy=str(data.get('policy', cache_lib.DEFAULT_POLICY)),
            miss_cost_usd=float(data.get('miss_cost_usd', cache_lib.DEFAULT_MISS_COST_USD)),
            hit_cost_usd=float(data.get('hit_cost_usd', cache_lib.DEFAULT_HIT_COST_USD)),
            miss_latency_ms=float(data.get('miss_latency_ms', cache_lib.DEFAULT_MISS_LATENCY_MS)),
            hit_latency_ms=float(data.get('hit_latency_ms', cache_lib.DEFAULT_HIT_LATENCY_MS)),
        )
        return jsonify({'success': True, 'simulation': sim, 'workload_size': len(workload)})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/cache/sweep', methods=['POST'])
def cache_sweep():
    try:
        data = request.get_json(silent=True) or {}
        workload = _cache_resolve_workload(data)
        if not workload:
            return jsonify({'success': False, 'error': 'workload is empty'}), 400
        thresholds = data.get('thresholds')
        if not (isinstance(thresholds, list) and thresholds):
            thresholds = list(cache_lib.THRESHOLD_SWEEP)
        curve = cache_lib.sweep_thresholds(
            workload,
            policy=str(data.get('policy', cache_lib.DEFAULT_POLICY)),
            capacity=int(data.get('capacity', cache_lib.DEFAULT_CAPACITY)),
            ttl_seconds=int(data.get('ttl_seconds', cache_lib.DEFAULT_TTL_SECONDS)),
            thresholds=[float(t) for t in thresholds],
        )
        grid = cache_lib.sweep_policies(
            workload,
            capacity=int(data.get('capacity', cache_lib.DEFAULT_CAPACITY)),
            ttl_seconds=int(data.get('ttl_seconds', cache_lib.DEFAULT_TTL_SECONDS)),
            thresholds=[float(t) for t in thresholds],
        )
        return jsonify({'success': True, 'curve': curve, 'grid': grid})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/cache/recommend', methods=['POST'])
def cache_recommend():
    try:
        data = request.get_json(silent=True) or {}
        workload = _cache_resolve_workload(data)
        if not workload:
            return jsonify({'success': False, 'error': 'workload is empty'}), 400
        picks = cache_lib.recommend_configs(
            workload,
            capacity=int(data.get('capacity', cache_lib.DEFAULT_CAPACITY)),
            ttl_seconds=int(data.get('ttl_seconds', cache_lib.DEFAULT_TTL_SECONDS)),
            monthly_requests=int(data.get('monthly_requests', cache_lib.DEFAULT_MONTHLY_REQUESTS)),
            quality_risk_ceiling=float(data.get('quality_risk_ceiling', 0.08)),
            miss_cost_usd=float(data.get('miss_cost_usd', cache_lib.DEFAULT_MISS_COST_USD)),
            hit_cost_usd=float(data.get('hit_cost_usd', cache_lib.DEFAULT_HIT_COST_USD)),
        )
        return jsonify({'success': True, 'recommendations': picks})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/cache/cluster', methods=['POST'])
def cache_cluster():
    try:
        data = request.get_json(silent=True) or {}
        workload = _cache_resolve_workload(data)
        if not workload:
            return jsonify({'success': False, 'error': 'workload is empty'}), 400
        clusters = cache_lib.cluster_workload(
            workload,
            threshold=float(data.get('threshold', cache_lib.DEFAULT_THRESHOLD)),
        )
        return jsonify({'success': True, 'clusters': clusters})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/cache/compile', methods=['POST'])
def cache_compile():
    try:
        data = request.get_json(silent=True) or {}
        workload = None
        if 'workload' in data or 'workload_id' in data:
            workload = _cache_resolve_workload(data)
        config = cache_lib.compile_cache(
            policy=str(data.get('policy', cache_lib.DEFAULT_POLICY)),
            threshold=float(data.get('threshold', cache_lib.DEFAULT_THRESHOLD)),
            capacity=int(data.get('capacity', cache_lib.DEFAULT_CAPACITY)),
            ttl_seconds=int(data.get('ttl_seconds', cache_lib.DEFAULT_TTL_SECONDS)),
            monthly_requests=int(data.get('monthly_requests', cache_lib.DEFAULT_MONTHLY_REQUESTS)),
            quality_risk_ceiling=float(data.get('quality_risk_ceiling', 0.08)),
            workload=workload,
        )
        return jsonify({
            'success': True,
            'config': config,
            'markdown': cache_lib.cache_markdown(config),
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/cache/seed', methods=['GET', 'POST'])
def cache_seed():
    try:
        return jsonify({'success': True, 'seed': cache_lib.seed_demo()})
    except Exception as e:  # pragma: no cover - defensive
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
