"""Draft synchronous API analysis driver. No persistence, logging, or native chats."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from outbound_http import OutboundError, json_request, opener_for


class RuntimeError(Exception):
    """Only fixed error codes escape; upstream bodies and exception text are private."""
    def __init__(self, code, *, outcome_unknown=False, diagnostic=None):
        super().__init__(code)
        self.code, self.outcome_unknown = code, outcome_unknown
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class Config:
    provider: str
    model: str
    credential_env: str
    endpoint: str = ""
    capability: str = "hub-result"
    max_turns: int = 8
    max_tools: int = 16
    timeout: float = 20
    deadline: float = 120
    max_output_tokens: int = 4096
    max_bytes: int = 512_000
    chat_token_field: str = "max_completion_tokens"
    network_mode: str = "direct"
    auth_method: str = "api_key"

    def __post_init__(self):
        if self.auth_method not in ('api_key','chatgpt_oauth') or (self.auth_method=='chatgpt_oauth' and self.provider!='responses'):
            raise RuntimeError('unsupported_auth_method')
        if self.network_mode not in ('direct', 'system'):
            raise RuntimeError('invalid_network_mode')
        if self.provider not in ("responses", "anthropic", "gemini", "chat"):
            raise RuntimeError("unsupported_provider")
        if self.capability != "hub-result":
            raise RuntimeError("native_chat_unsupported")
        if not isinstance(self.model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", self.model):
            raise RuntimeError("invalid_model")
        if not isinstance(self.credential_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", self.credential_env):
            raise RuntimeError("invalid_credential_reference")
        for value, upper in ((self.max_turns, 32), (self.max_tools, 64),
                             (self.max_output_tokens, 32000), (self.max_bytes, 2_000_000)):
            if type(value) is not int or not 1 <= value <= upper:
                raise RuntimeError("invalid_limit")
        if (type(self.timeout) not in (int, float) or type(self.deadline) not in (int, float)
                or not math.isfinite(self.timeout) or not math.isfinite(self.deadline)
                or not 0 < self.timeout <= 60 or not 0 < self.deadline <= 600):
            raise RuntimeError("invalid_limit")
        if self.chat_token_field not in ("max_tokens", "max_completion_tokens"):
            raise RuntimeError("unsupported_chat_contract")
        # Only compatible providers accept an explicitly trusted endpoint.
        if self.endpoint and self.provider != "chat":
            raise RuntimeError("endpoint_override_unsupported")
        if self.endpoint:
            try:
                p = urllib.parse.urlsplit(self.endpoint)
                p.port  # Validate bounds before saving or loading any credential.
            except (ValueError, TypeError, AttributeError):
                raise RuntimeError('invalid_endpoint') from None
            if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
                raise RuntimeError("invalid_endpoint")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


def load_config(path, *, forbidden_roots):
    """Read metadata only from external private configuration; keys use env refs.

    Host supplies both installed app and source roots. No file creation or ACL changes.
    """
    p = Path(path)
    if not p.is_absolute() or not forbidden_roots:
        raise RuntimeError("external_config_required")
    for ancestor in (p, *p.parents):
        if ancestor.exists():
            stat = ancestor.lstat()
            if ancestor.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise RuntimeError("unsafe_config_path")
    resolved = p.resolve()
    if any(resolved.is_relative_to(Path(root).resolve()) for root in forbidden_roots):
        raise RuntimeError("external_config_required")
    try:
        with p.open("rb") as handle:
            raw = handle.read(16_001)
        if len(raw) > 16_000:
            raise ValueError()
        return Config(**json.loads(raw))
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("invalid_private_config") from None


class HTTP:
    def __init__(self, network_mode='direct', observer=None):
        self.network_mode, self.observer = network_mode, observer
        self.opener = None
        self.diagnostics = []

    def observe(self, value):
        self.diagnostics = [item for item in self.diagnostics if item['requestId'] != value['requestId']][-31:] + [value]
        if self.observer:
            self.observer(deepcopy(self.diagnostics))

    def __call__(self, url, headers, body, timeout, limit):
        responses_stream = body.get('stream') is True and url == 'https://api.openai.com/v1/responses'
        request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                        headers={**headers, "Content-Type": "application/json",
                                                 **({'Accept': 'text/event-stream'} if responses_stream else {})}, method="POST")
        try:
            return json_request(request, opener=self.opener or opener_for(url, self.network_mode),
                timeout=timeout, limit=limit, network_mode=self.network_mode, observer=self.observe,
                responses_stream=responses_stream)[0]
        except OutboundError as error:
            category = error.diagnostic['category']
            code = ('provider_http_error' if 'httpStatus' in error.diagnostic and category != 'parse'
                    else 'provider_' + category)
            raise RuntimeError(code, outcome_unknown=error.outcome_unknown, diagnostic=error.diagnostic) from None


def probe(config, key, transport):
    """Explicit single-turn probe with its own bounded wait; no tools or context.

    Probes use a 60-second network inactivity timeout, independent of the
    multi-turn analysis timeout, and respect a shorter overall deadline.
    """
    headers = {'Authorization': 'Bearer ' + key}
    prompt = 'Reply OK.'
    if config.provider == 'responses':
        url = 'https://api.openai.com/v1/responses'
        body = dict(model=config.model, input=prompt, max_output_tokens=16, store=False)
        if config.auth_method=='chatgpt_oauth':
            body=dict(model=config.model,input=[dict(role='user',content=prompt)],store=False,stream=True)
    elif config.provider == 'anthropic':
        url = 'https://api.anthropic.com/v1/messages'
        headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
        body = dict(model=config.model, messages=[dict(role='user', content=prompt)], max_tokens=16)
    elif config.provider == 'gemini':
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + urllib.parse.quote(config.model, safe='') + ':generateContent'
        headers = {'x-goog-api-key': key}
        body = dict(contents=[dict(role='user', parts=[dict(text=prompt)])], generationConfig=dict(maxOutputTokens=16))
    else:
        url = config.endpoint or 'https://api.openai.com/v1/chat/completions'
        body = dict(model=config.model, messages=[dict(role='user', content=prompt)])
        body[config.chat_token_field] = 16
        if not config.endpoint:
            body['store'] = False
    value = transport(url, headers, body, min(config.deadline, 60), min(config.max_bytes, 64000))
    valid = (config.provider == 'responses' and value.get('status') in ('completed', 'incomplete') and isinstance(value.get('output'), list)
             or config.provider == 'anthropic' and isinstance(value.get('content'), list) and value.get('stop_reason') in ('end_turn', 'max_tokens')
             or config.provider == 'gemini' and isinstance(value.get('candidates'), list) and bool(value['candidates'])
             or config.provider == 'chat' and isinstance(value.get('choices'), list) and bool(value['choices']) and isinstance(value['choices'][0].get('message'), dict))
    if not valid:
        diagnostic = dict(transport.diagnostics[-1], status='failed', category='parse', phase='parse', outcomeUnknown=True)
        transport.observe(diagnostic)
        raise RuntimeError('malformed_provider_response', outcome_unknown=True, diagnostic=diagnostic)


class HubTools:
    """Broker uses the real agent_sdk.Client; it never gives the model a token/session.

    Server authentication remains authoritative. Descriptor/action grants are selected
    by trusted host policy, never supplied by model text or a browser request.
    """
    READ_ACTIONS = {"hub_context": None,
                    "hub_knowledge": {"context", "search", "read", "history", "job", "import-read", "impact"}}

    def __init__(self, client, project, descriptors, *, trusted_host_grants=None):
        if not client.session or not project:
            raise RuntimeError("binding_required")
        self.client, self.project = client, project
        self.descriptors = deepcopy(descriptors)
        grants = self.READ_ACTIONS if trusted_host_grants is None else trusted_host_grants
        if not isinstance(grants, dict):
            raise RuntimeError("tool_scope_unsupported")
        self.grants = {name: None if actions is None else frozenset(actions)
                       for name, actions in grants.items()}
        self.names = {d["name"] for d in self.descriptors}
        if len(self.names) != len(self.descriptors) or not self.names <= self.grants.keys():
            raise RuntimeError("tool_scope_unsupported")
        for descriptor in self.descriptors:
            schema = descriptor["inputSchema"]
            for private in ("session", "project", "cwd"):
                schema.get("properties", {}).pop(private, None)
            schema["required"] = [v for v in schema.get("required", []) if v not in ("session", "project", "cwd")]
            schema["additionalProperties"] = False

    def verify(self):
        try:
            value = self.client.call("hub_context", {})
        except Exception:
            raise RuntimeError("hub_binding_unavailable") from None
        if not isinstance(value, dict) or value.get("connection", {}).get("project") != self.project:
            raise RuntimeError("project_binding_mismatch")

    def call(self, name, arguments, timeout):
        if name not in self.names or not isinstance(arguments, dict):
            raise RuntimeError("tool_scope_denied")
        if any(k in arguments for k in ("session", "project", "cwd")):
            raise RuntimeError("tool_binding_override")
        actions = self.grants[name]
        if actions is not None and arguments.get("action") not in actions:
            raise RuntimeError("tool_action_denied")
        previous = self.client.timeout
        try:
            self.client.timeout = timeout
            return self.client.call(name, arguments)
        except Exception:
            raise RuntimeError("hub_tool_failed") from None
        finally:
            self.client.timeout = previous


class Driver:
    def __init__(self, config, broker, *, transport=None, environ=None, clock=time.monotonic):
        self.config, self.broker = config, broker
        self.transport, self.clock = transport or HTTP(config.network_mode), clock
        self._key = (os.environ if environ is None else environ).get(config.credential_env)
        if not isinstance(self._key, str) or not self._key or any(ord(c) < 33 for c in self._key):
            raise RuntimeError("credential_unavailable")

    @staticmethod
    def capabilities():
        return {"hubResult": True, "nativeChat": False, "streaming": False, "resume": False}

    def _public(self, value):
        # Credentials never enter transcripts/results; reject even an upstream echo.
        encoded = json.dumps(value, ensure_ascii=False)
        secrets = (self._key, getattr(self.broker.client, "token", None))
        def contains(item):
            if isinstance(item, str):
                return any(secret and secret in item for secret in secrets)
            if isinstance(item, dict):
                return any(contains(k) or contains(v) for k, v in item.items())
            if isinstance(item, list):
                return any(contains(v) for v in item)
            return False
        if contains(value):
            raise RuntimeError("credential_echo_rejected")
        if len(encoded.encode()) > self.config.max_bytes:
            raise RuntimeError("context_limit")
        return value

    def run(self, prompt, *, instructions="Analyze using only permitted Hub reads.", cancel=None):
        c, kind = self.config, self.config.provider
        started, calls = self.clock(), 0

        def remaining():
            if cancel is not None and cancel.is_set():
                raise RuntimeError("cancelled")
            left = c.deadline - (self.clock() - started)
            if left <= 0:
                raise RuntimeError("deadline_exceeded")
            return min(c.timeout, left)

        remaining()
        previous = self.broker.client.timeout
        try:
            self.broker.client.timeout = remaining()
            self.broker.verify()
        finally:
            self.broker.client.timeout = previous
        history = [{"role": "user", "content": prompt}]
        if kind == "gemini":
            history = [{"role": "user", "parts": [{"text": prompt}]}]
        if kind == "chat":
            history.insert(0, {"role": "system", "content": instructions})
        definitions = [{"name": d["name"], "description": d.get("description", ""),
                        "parameters": d["inputSchema"]} for d in self.broker.descriptors]
        finalized_for_budget = False
        for turn in range(c.max_turns):
            finalizing = turn + 1 == c.max_turns or calls >= c.max_tools
            finalized_for_budget = finalized_for_budget or finalizing
            turn_definitions = [] if finalizing else definitions
            turn_instructions = instructions + (
                '\nRead budget exhausted. No further tool calls are permitted. Return the requested final result '
                'using only already inspected evidence. State coverage limitations; do not invent findings.'
                if finalizing else f'\nRemaining budget: {c.max_tools - calls} tool calls, '
                f'{c.max_turns - turn - 1} reading turns, then one final answer. '
                'Read only what is essential and leave time to summarize inspected evidence.')
            headers = {"Authorization": "Bearer " + self._key}
            body = {"model": c.model}
            if kind == "responses":
                url = "https://api.openai.com/v1/responses"
                body.update(input=history, instructions=turn_instructions, store=False,
                            include=["reasoning.encrypted_content"], max_output_tokens=c.max_output_tokens,
                            tools=[dict(type="function", strict=False, **d) for d in turn_definitions])
                if c.auth_method=='chatgpt_oauth':
                    body.pop('max_output_tokens')
                    tools=body.pop('tools')
                    body.update(stream=True,input=([dict(type='additional_tools',role='developer',tools=tools)] if tools else [])+history)
            elif kind == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01"}
                body.update(messages=history, system=turn_instructions, max_tokens=c.max_output_tokens,
                            tools=[dict(name=d["name"], description=d["description"], input_schema=d["parameters"]) for d in turn_definitions])
            elif kind == "gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(c.model, safe="") + ":generateContent"
                headers = {"x-goog-api-key": self._key}
                body = dict(contents=history, systemInstruction={"parts": [{"text": turn_instructions}]},
                            generationConfig={"maxOutputTokens": c.max_output_tokens},
                            tools=[{"functionDeclarations": [dict(name=d["name"], description=d["description"],
                                parametersJsonSchema=d["parameters"]) for d in turn_definitions]}])
            else:
                url = c.endpoint or "https://api.openai.com/v1/chat/completions"
                history[0]['content'] = turn_instructions
                body.update(messages=history, tools=[dict(type="function", function=d) for d in turn_definitions])
                body[c.chat_token_field] = c.max_output_tokens
                # OpenAI's default endpoint supports store; arbitrary compatible APIs may not.
                if not c.endpoint:
                    body["store"] = False
            if finalizing:
                body.pop('tools', None)
            self._public(body)
            try:
                reply = self.transport(url, headers, deepcopy(body), remaining(), c.max_bytes)
                remaining()
                self._public(reply)
                pending, text = self._parse(kind, reply, history)
            except RuntimeError:
                raise
            except Exception:
                raise RuntimeError("malformed_provider_response", outcome_unknown=True) from None
            if not pending:
                if not text:
                    raise RuntimeError("empty_result")
                return self._public(dict(kind="hub-result", project=self.broker.project,
                                         provider=kind, model=c.model, text=text, turns=turn + 1, toolCalls=calls,
                                         finalizedForBudget=finalized_for_budget))
            if finalizing:
                raise RuntimeError("loop_limit")
            # Validate ALL calls before dispatch; avoid partial batches on scope errors.
            ids = [p[0] for p in pending if p[0]]
            if len(ids) != len(set(ids)):
                raise RuntimeError("duplicate_tool_call")
            for _, name, args in pending:
                if name not in self.broker.names or not isinstance(args, dict):
                    raise RuntimeError("tool_scope_denied")
                if any(k in args for k in ("session", "project", "cwd")):
                    raise RuntimeError("tool_binding_override")
                actions = self.broker.grants[name]
                if actions is not None and args.get("action") not in actions:
                    raise RuntimeError("tool_action_denied")
            results = []
            for call_id, name, args in pending:
                if calls >= c.max_tools:
                    results.append((call_id, name, dict(error=dict(code='tool_budget_exhausted',
                        message='No further reads permitted. Finish using inspected evidence and state limitations.'))))
                    continue
                value = self._public(self.broker.call(name, args, remaining()))
                remaining()
                calls += 1
                results.append((call_id, name, value))
            if kind == "responses":
                history.extend(dict(type="function_call_output", call_id=i, output=json.dumps(v)) for i, _, v in results)
            elif kind == "anthropic":
                history.append(dict(role="user", content=[dict(type="tool_result", tool_use_id=i, content=json.dumps(v)) for i, _, v in results]))
            elif kind == "gemini":
                parts = []
                for i, name, value in results:
                    result = dict(name=name, response=value if isinstance(value, dict) else {"result": value})
                    if i:
                        result["id"] = i
                    parts.append({"functionResponse": result})
                history.append(dict(role="user", parts=parts))
            else:
                history.extend(dict(role="tool", tool_call_id=i, content=json.dumps(v)) for i, _, v in results)
        raise RuntimeError("loop_limit")

    @staticmethod
    def _parse(kind, reply, history):
        pending, texts = [], []
        if kind == "responses":
            if reply.get("status") != "completed":
                raise RuntimeError("provider_incomplete")
            blocks = reply["output"]
            history.extend(deepcopy(blocks))
            for b in blocks:
                if b["type"] == "function_call":
                    pending.append((b["call_id"], b["name"], json.loads(b["arguments"])))
                elif b["type"] == "message":
                    texts.extend(p["text"] for p in b["content"] if p["type"] == "output_text")
        elif kind == "anthropic":
            if reply.get("stop_reason") not in ("end_turn", "tool_use"):
                raise RuntimeError("provider_incomplete")
            blocks = reply["content"]
            history.append(dict(role="assistant", content=deepcopy(blocks)))
            for b in blocks:
                if b["type"] == "tool_use":
                    pending.append((b["id"], b["name"], b["input"]))
                elif b["type"] == "text":
                    texts.append(b["text"])
        elif kind == "gemini":
            candidate = reply["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise RuntimeError("provider_incomplete")
            content = candidate["content"]
            history.append(deepcopy(content))  # Includes thoughtSignature exactly.
            for p in content["parts"]:
                if "functionCall" in p:
                    b = p["functionCall"]
                    pending.append((b.get("id", ""), b["name"], b.get("args", {})))
                elif "text" in p and not p.get("thought"):
                    texts.append(p["text"])
        else:
            choice = reply["choices"][0]
            if choice["finish_reason"] not in ("stop", "tool_calls"):
                raise RuntimeError("provider_incomplete")
            message = choice["message"]
            history.append(deepcopy(message))
            for b in message.get("tool_calls", []):
                pending.append((b["id"], b["function"]["name"], json.loads(b["function"]["arguments"])))
            if message.get("content"):
                texts.append(message["content"])
        return pending, "\n".join(texts)
