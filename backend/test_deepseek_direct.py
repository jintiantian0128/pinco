import json
import unittest
from unittest.mock import patch

import main


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class FakeStreamResponse(FakeResponse):
    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


class BrokenStreamResponse(FakeStreamResponse):
    def __iter__(self):
        yield from self.body.splitlines(keepends=True)
        raise main.URLError("connection reset")


class DeepSeekDirectRequestTests(unittest.TestCase):
    def test_chat_calls_deepseek_http_endpoint_without_sdk(self):
        body = json.dumps({"choices": [{"message": {"content": "收到，我来帮你梳理。"}}]}).encode()
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"), \
             patch.object(main, "urlopen", return_value=FakeResponse(body)) as request_call:
            result = main._deepseek_chat_request({"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(result, "收到，我来帮你梳理。")
        request = request_call.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer unit-test-key")
        self.assertEqual(json.loads(request.data), {"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]})
        request_call.assert_called_once()

    def test_native_base_url_uses_deepseek_chat_route(self):
        self.assertEqual(
            main.deepseek_chat_completions_url("https://api.deepseek.com"),
            "https://api.deepseek.com/chat/completions",
        )

    def test_career_chat_can_disable_hidden_thinking_for_first_token_latency(self):
        body = json.dumps({"choices": [{"message": {"content": "{\\\"response\\\":\\\"收到\\\"}"}}]}).encode()
        with patch.object(main, "MOCK_MODE", False), \
             patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "DEFAULT_MODEL", "deepseek-v4-flash"), \
             patch.object(main, "urlopen", return_value=FakeResponse(body)) as request_call:
            result = main.llm_chat(
                [{"role": "user", "content": "请简短回答"}],
                system_prompt="只输出合法 JSON。",
                max_tokens=1800,
                thinking="disabled",
            )

        self.assertIn("收到", result)
        payload = json.loads(request_call.call_args.args[0].data)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["max_tokens"], 1800)

    def test_llm_health_probe_uses_nonthinking_output_budget(self):
        with patch.object(main, "MOCK_MODE", False), \
             patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "DEFAULT_MODEL", "deepseek-v4-flash"), \
             patch.object(main, "_llm_probe_cache", {"checked_at": 0, "status": None}), \
             patch.object(main, "llm_chat", return_value="OK") as chat_call:
            result = main.probe_llm(force=True)

        self.assertTrue(result["online"])
        self.assertEqual(chat_call.call_args.kwargs["max_tokens"], 16)
        self.assertEqual(chat_call.call_args.kwargs["thinking"], "disabled")

    def test_internal_next_action_is_never_exposed_verbatim(self):
        raw = {"response": "请告诉我你的方向。", "next_action": "ask_user_to_choose_direction"}
        result = main.sanitize_agent_result(raw)
        self.assertEqual(result["next_action"], "先选一个想优先解决的方向，也可以直接描述你的经历。")

        raw["next_action"] = "internal_planner_step"
        self.assertEqual(main.sanitize_agent_result(raw)["next_action"], "")

    def test_transient_rate_limit_is_retried_once_then_succeeds(self):
        from urllib.error import HTTPError

        error = HTTPError("https://api.deepseek.com/chat/completions", 429, "limited", {}, None)
        body = json.dumps({"choices": [{"message": {"content": "恢复成功"}, "finish_reason": "stop"}]}).encode()
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=[error, FakeResponse(body)]) as request_call, \
             patch.object(main, "wait_before_deepseek_retry"):
            result = main._deepseek_chat_request({"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(result, "恢复成功")
        self.assertEqual(request_call.call_count, 2)

    def test_empty_completion_is_retried_once(self):
        empty = json.dumps({"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]}).encode()
        valid = json.dumps({"choices": [{"message": {"content": "这次有内容"}, "finish_reason": "stop"}]}).encode()
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=[FakeResponse(empty), FakeResponse(valid)]) as request_call, \
             patch.object(main, "wait_before_deepseek_retry"):
            result = main._deepseek_chat_request({"model": "deepseek-v4-flash", "messages": []})
        self.assertEqual(result, "这次有内容")
        self.assertEqual(request_call.call_count, 2)

    def test_auth_failure_is_not_retried_and_balance_is_classified(self):
        from urllib.error import HTTPError

        error = HTTPError("https://api.deepseek.com/chat/completions", 401, "invalid key", {}, None)
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=error) as request_call:
            with self.assertRaises(main.DeepSeekAPIError):
                main._deepseek_chat_request({"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]})
        request_call.assert_called_once()
        self.assertEqual(main.llm_http_exception(main.DeepSeekAPIError(402, "Insufficient Balance")).status_code, 402)

    def test_stream_request_sets_stream_true_and_forwards_provider_deltas(self):
        provider_chunks = ['{"response":"Hi', ' there","intent":"x"}']
        body = b""
        for chunk in provider_chunks:
            event = json.dumps({"choices": [{"delta": {"content": chunk}}]})
            body += f"data: {event}\n\n".encode()
        body += b"data: [DONE]\n\n"
        deltas = []
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", return_value=FakeStreamResponse(body)) as request_call:
            result = main._deepseek_chat_request_stream({"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]}, deltas.append)

        request = request_call.call_args.args[0]
        self.assertTrue(json.loads(request.data)["stream"])
        self.assertEqual(result, ''.join(deltas))
        self.assertEqual(result, '{"response":"Hi there","intent":"x"}')

    def test_stream_retries_transient_failure_before_first_delta(self):
        from urllib.error import HTTPError

        error = HTTPError("https://api.deepseek.com/chat/completions", 503, "overloaded", {}, None)
        body = (f"data: {json.dumps({'choices': [{'delta': {'content': 'ready'}, 'finish_reason': None}]})}\n\n"
                "data: [DONE]\n\n").encode()
        deltas = []
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=[error, FakeStreamResponse(body)]) as request_call, \
             patch.object(main, "wait_before_deepseek_retry"):
            result = main._deepseek_chat_request_stream({"model": "deepseek-v4-flash", "messages": []}, deltas.append)
        self.assertEqual(result, "ready")
        self.assertEqual(deltas, ["ready"])
        self.assertEqual(request_call.call_count, 2)

    def test_stream_retries_transport_failure_before_first_delta(self):
        body = f"data: {json.dumps({'choices': [{'delta': {'content': 'recovered'}, 'finish_reason': None}]})}\n\n".encode()
        deltas = []
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=[BrokenStreamResponse(b""), FakeStreamResponse(body)]) as request_call, \
             patch.object(main, "wait_before_deepseek_retry"):
            result = main._deepseek_chat_request_stream({"model": "deepseek-v4-flash", "messages": []}, deltas.append)
        self.assertEqual(result, "recovered")
        self.assertEqual(deltas, ["recovered"])
        self.assertEqual(request_call.call_count, 2)

    def test_stream_does_not_retry_after_partial_output(self):
        body = f"data: {json.dumps({'choices': [{'delta': {'content': 'partial'}, 'finish_reason': None}]})}\n\n".encode()
        deltas = []
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", return_value=BrokenStreamResponse(body)) as request_call:
            with self.assertRaisesRegex(RuntimeError, "streaming transport error"):
                main._deepseek_chat_request_stream({"model": "deepseek-v4-flash", "messages": []}, deltas.append)
        self.assertEqual(deltas, ["partial"])
        request_call.assert_called_once()

    def test_json_field_streamer_decodes_split_escapes_without_leaking_wrapper(self):
        streamer = main._JsonStringFieldStreamer("response")
        output = ''.join([
            streamer.feed('{"intent":"career","response":"你好\\n'),
            streamer.feed('继续\\"问\\u4f60"}'),
        ])
        self.assertEqual(output, '你好\n继续"问你')


if __name__ == "__main__":
    unittest.main()
