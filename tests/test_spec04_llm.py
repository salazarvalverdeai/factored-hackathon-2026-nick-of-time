"""Shared LLM client and config.resolve (spec 04 T7a, supports AC-14; decisions D-011 and D-016).
Offline: a stubbed boto3 client asserts the Converse request shape. No test calls a real model."""
import os

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ParamValidationError

from nick_of_time.config import HAIKU, SONNET, resolve
from nick_of_time.llm import FakeClient, NoStructuredOutput, ProviderUnavailable, make_client
from nick_of_time.llm.bedrock import BedrockClient

SCHEMA = {"type": "object", "properties": {"intent": {"type": "string"}}}
PRICES = {"input_per_1m": 1.1, "output_per_1m": 5.5}


def client_error(code, msg="x"):
    return ClientError({"Error": {"Code": code, "Message": msg}}, "Converse")


class StubBoto:
    """Answers `converse` from a script of replies or exceptions and keeps every request."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def converse(self, **req):
        self.requests.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


OK_TOOL = {"output": {"message": {"content": [{"toolUse": {"name": "record_output", "input": {"intent": "dispute"}}}]}},
           "stopReason": "tool_use", "usage": {"inputTokens": 1000, "outputTokens": 200}}


def bedrock(*script, **kw):
    stub = StubBoto(*script)
    return BedrockClient("us.anthropic.claude-haiku-4-5-20251001-v1:0", boto_client=stub, prices=PRICES, **kw), stub


def test_request_shape_tool_mode_temperature_zero_and_usage():
    """T7a / D-011 / D-016: forced tool use, maxTokens, temperature 0, tokens and cost from the price table."""
    c, stub = bedrock(OK_TOOL)
    r = c.complete("sys", "hola", schema=SCHEMA, max_tokens=300)
    req = stub.requests[0]
    assert req["modelId"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert req["inferenceConfig"] == {"maxTokens": 300, "temperature": 0}
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "record_output"}}
    assert req["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"] == {"json": SCHEMA}
    assert (r.tool_input, r.mode, r.temperature, r.tokens_in, r.tokens_out) == ({"intent": "dispute"}, "tool", 0, 1000, 200)
    assert r.cost_usd == pytest.approx((1000 * 1.1 + 200 * 5.5) / 1e6)


def test_no_schema_sends_no_tool_config():
    c, stub = bedrock({"output": {"message": {"content": [{"text": "hola"}]}}, "stopReason": "end_turn"})
    r = c.complete("s", "u")
    assert "toolConfig" not in stub.requests[0] and (r.text, r.mode) == ("hola", None)


def test_ladder_steps_down_and_records_mode_d011():
    """D-011: tool rejected -> any; the accepted mode is kept and the next call starts there."""
    c, stub = bedrock(client_error("ValidationException", "This model doesn't support toolChoice tool"), OK_TOOL, OK_TOOL)
    assert c.complete("s", "u", schema=SCHEMA).mode == "any"
    assert stub.requests[1]["toolConfig"]["toolChoice"] == {"any": {}}
    c.complete("s", "u", schema=SCHEMA)
    assert stub.requests[2]["toolConfig"]["toolChoice"] == {"any": {}}


def test_ladder_exhausted_is_no_structured_output_d011():
    rej = client_error("ValidationException", "toolChoice is not supported")
    c, stub = bedrock(rej, rej, rej)
    with pytest.raises(ProviderUnavailable):   # the graph degrades to S0 (spec 04 section 5)
        c.complete("s", "u", schema=SCHEMA)
    assert [r["toolConfig"]["toolChoice"] for r in stub.requests] == [{"tool": {"name": "record_output"}},
                                                                      {"any": {}}, {"auto": {}}]


def test_latency_ms_is_measured():
    c, _ = bedrock(OK_TOOL)
    assert c.complete("s", "u", schema=SCHEMA).latency_ms >= 0


@pytest.mark.parametrize("reply", [
    {"output": {"message": {"content": [{"text": "no tool"}]}}, "stopReason": "end_turn"},
    {**OK_TOOL, "output": {"message": {"content": [{"toolUse": {"name": "record_output", "input": {"intent": 3}}}]}}}])
def test_no_or_invalid_tool_input_is_no_structured_output(reply):
    c, _ = bedrock(reply)
    with pytest.raises(NoStructuredOutput) as e:
        c.complete("s", "u", schema=SCHEMA)
    assert not isinstance(e.value, ProviderUnavailable)


def test_bedrock_error_message_is_truncated():
    c, _ = bedrock(client_error("AccessDeniedException", "arn:aws:iam::123456789012:user/x " * 50))
    with pytest.raises(ProviderUnavailable) as e:
        c.complete("s", "u")
    assert len(str(e.value)) <= 300


def test_botocore_stubber_validates_request_shape():
    import boto3
    from botocore.stub import Stubber
    client = boto3.client("bedrock-runtime", region_name="us-east-2", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as st:
        st.add_response("converse", {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t", "name": "record_output", "input": {"intent": "d"}}}]}},
            "stopReason": "tool_use", "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "metrics": {"latencyMs": 1}})
        r = BedrockClient("us.anthropic.claude-sonnet-4-6", boto_client=client).complete("s", "u", schema=SCHEMA)
    assert r.tool_input == {"intent": "d"}


def test_temperature_rejected_retries_without_it_d016():
    """D-016: a model that rejects temperature gets the provider default; the result records None."""
    c, stub = bedrock(client_error("ValidationException", "temperature is not supported for this model"), OK_TOOL)
    r = c.complete("s", "u", schema=SCHEMA)
    assert "temperature" in stub.requests[0]["inferenceConfig"]
    assert "temperature" not in stub.requests[1]["inferenceConfig"] and r.temperature is None


@pytest.mark.parametrize("code", ["ThrottlingException", "AccessDeniedException", "ServiceQuotaExceededException"])
def test_provider_errors_become_provider_unavailable(code):
    c, _ = bedrock(client_error(code))
    with pytest.raises(ProviderUnavailable, match=code):
        c.complete("s", "u", schema=SCHEMA)


def test_connection_and_wrong_model_id_are_unavailable():
    c, _ = bedrock(EndpointConnectionError(endpoint_url="https://x"))
    with pytest.raises(ProviderUnavailable):
        c.complete("s", "u")
    c, _ = bedrock(client_error("ValidationException", "The provided model identifier is invalid."))
    with pytest.raises(ProviderUnavailable, match="config"):
        c.complete("s", "u")


def test_our_malformed_requests_reraise():
    c, _ = bedrock(ParamValidationError(report="bad"))
    with pytest.raises(ParamValidationError):
        c.complete("s", "u")
    c, _ = bedrock(client_error("ValidationException", "inputSchema is malformed"))
    with pytest.raises(ClientError):
        c.complete("s", "u", schema=SCHEMA)


def test_fake_is_scripted_and_deterministic():
    f = FakeClient(script=["hola", {"intent": "x"}, ProviderUnavailable("down")])
    assert f.complete("s", "u").text == "hola"
    r = f.complete("s", "u", schema=SCHEMA)
    assert r.tool_input == {"intent": "x"} and r.cost_usd is None and f.calls[1]["mode"] == "tool"
    with pytest.raises(ProviderUnavailable):
        f.complete("s", "u")
    with pytest.raises(ProviderUnavailable):   # exhausted script degrades like an unconfigured provider
        f.complete("s", "u")


def test_resolve_arms_and_env_names():
    """Spec 01 6.8 arms and 6.9 names: S0 no LLM, S1 fast model, S2 graph model; unset provider is fake."""
    assert not resolve("S0", {}).uses_llm
    assert resolve("S1", {}) .model == HAIKU and resolve("S2", {}).model == SONNET
    assert resolve("S1", {}).provider == "fake"
    env = {"LLM_PROVIDER": "bedrock", "BEDROCK_MODEL_FAST": "fast-id", "BEDROCK_MODEL_GRAPH": "graph-id"}
    assert (resolve("S1", env).provider, resolve("S1", env).model, resolve("S2", env).model) == ("bedrock", "fast-id", "graph-id")
    assert resolve("jev2", env, extra={"jev2": {"model": "m", "temperature": None}}).temperature is None
    with pytest.raises(ValueError):
        resolve("S9", env)
    with pytest.raises(ValueError):
        resolve("S1", {"LLM_PROVIDER": "openai"})


def test_make_client_by_provider(monkeypatch):
    f = make_client(resolve("S1", {}), script=["ok"])
    assert isinstance(f, FakeClient) and f.complete("s", "u").text == "ok"
    b = make_client(resolve("S2", {"LLM_PROVIDER": "bedrock"}), boto_client=StubBoto(), prices=PRICES)
    assert isinstance(b, BedrockClient) and b.model == SONNET
    with pytest.raises(ValueError):
        make_client(resolve("S0", {}))


def test_anthropic_fallback_request_and_errors():
    import anthropic
    import httpx2 as httpx   # the httpx the SDK actually uses
    from types import SimpleNamespace as NS
    from nick_of_time.llm.anthropic import AnthropicClient, api_model_id

    assert api_model_id(HAIKU) == "claude-haiku-4-5-20251001" and api_model_id(SONNET) == "claude-sonnet-4-6"
    assert api_model_id("global.anthropic.claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert api_model_id("anthropic.claude-haiku-4-5-20251001-v1:0") == "claude-haiku-4-5-20251001"
    with pytest.raises(ValueError):
        api_model_id("us.meta.llama3-1-70b-instruct-v1:0")
    seen = []
    msg = NS(content=[NS(type="tool_use", input={"intent": "d"})], stop_reason="tool_use",
             usage=NS(input_tokens=5, output_tokens=2))

    class SDK:
        messages = NS(create=lambda **kw: (seen.append(kw), msg)[1])
    r = AnthropicClient("claude-x", sdk_client=SDK).complete("s", "u", schema=SCHEMA)
    assert seen[0]["tool_choice"] == {"type": "tool", "name": "record_output"} and seen[0]["temperature"] == 0
    assert (r.tool_input, r.tokens_in) == ({"intent": "d"}, 5)

    req = httpx.Request("POST", "https://api.anthropic.com")
    def boom(**kw):
        raise anthropic.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)
    with pytest.raises(ProviderUnavailable):
        AnthropicClient("claude-x", sdk_client=NS(messages=NS(create=boom))).complete("s", "u")


@pytest.mark.skipif(not os.environ.get("LIVE_LLM"), reason="opt-in live call (manual step M11); never in CI")
def test_live_bedrock_smoke():
    r = make_client(resolve("S1", {**os.environ, "LLM_PROVIDER": "bedrock"})).complete("Reply briefly.", "hola")
    assert r.text
