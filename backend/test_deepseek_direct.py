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

    def test_rate_limit_is_not_retried(self):
        from urllib.error import HTTPError

        error = HTTPError("https://api.deepseek.com/chat/completions", 429, "limited", {}, None)
        with patch.object(main, "DEEPSEEK_API_KEY", "unit-test-key"), \
             patch.object(main, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"), \
             patch.object(main, "urlopen", side_effect=error) as request_call:
            with self.assertRaises(main.DeepSeekAPIError) as raised:
                main._deepseek_chat_request({"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(raised.exception.status_code, 429)
        request_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
