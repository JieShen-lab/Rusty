from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.ai_client import (
    AIConnectTimeoutError,
    AIReadTimeoutError,
    OpenAICompatibleClient,
)
from rusty.services.model_service import ModelConfig


def configured_model(timeout_seconds: int = 63) -> ModelConfig:
    return ModelConfig(
        id=1,
        display_name="Custom",
        provider="openai_compatible",
        base_url="https://custom.example/v1",
        model_name="custom-model",
        temperature=0.2,
        max_tokens=500,
        timeout_seconds=timeout_seconds,
        is_default=True,
        has_api_key=True,
    )


class AIClientTimeoutTests(unittest.TestCase):
    def test_generation_uses_saved_timeout_and_custom_base_url(self) -> None:
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.iter_lines.return_value = iter([
            'data: {"choices":[{"delta":{"content":"O"}}]}',
            'data: {"choices":[{"delta":{"content":"K"}}],"usage":{"total_tokens":2}}',
            "data: [DONE]",
        ])
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        context_client = mock.Mock()
        context_client.__enter__ = mock.Mock(return_value=context_client)
        context_client.__exit__ = mock.Mock(return_value=False)
        context_client.stream.return_value = response

        with mock.patch("httpx.Client", return_value=context_client) as client_factory:
            result = OpenAICompatibleClient(purpose="generation").chat(
                configured_model(63), "secret", [{"role": "user", "content": "test"}]
            )

        timeout = client_factory.call_args.kwargs["timeout"]
        self.assertEqual(10, timeout.connect)
        self.assertEqual(63, timeout.read)
        self.assertEqual(
            "https://custom.example/v1/chat/completions",
            context_client.stream.call_args.args[1],
        )
        self.assertTrue(context_client.stream.call_args.kwargs["json"]["stream"])
        self.assertEqual("OK", result.text)
        self.assertEqual({"total_tokens": 2}, result.token_usage)

    def test_connection_test_remains_a_short_non_streaming_request(self) -> None:
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        context_client = mock.Mock()
        context_client.__enter__ = mock.Mock(return_value=context_client)
        context_client.__exit__ = mock.Mock(return_value=False)
        context_client.post.return_value = response

        with mock.patch("httpx.Client", return_value=context_client):
            OpenAICompatibleClient(purpose="connection_test").chat(
                configured_model(63), "secret", [{"role": "user", "content": "test"}]
            )

        self.assertNotIn("stream", context_client.post.call_args.kwargs["json"])
        context_client.stream.assert_not_called()

    def test_connect_and_read_timeout_have_distinct_errors(self) -> None:
        request = httpx.Request("POST", "https://custom.example/v1/chat/completions")
        for provider_error, expected_error, message in (
            (httpx.ConnectTimeout("connect", request=request), AIConnectTimeoutError, "无法建立模型连接"),
            (httpx.ReadTimeout("read", request=request), AIReadTimeoutError, "已连接但响应超时"),
        ):
            context_client = mock.Mock()
            context_client.__enter__ = mock.Mock(return_value=context_client)
            context_client.__exit__ = mock.Mock(return_value=False)
            context_client.stream.side_effect = provider_error
            with (
                mock.patch("httpx.Client", return_value=context_client),
                self.assertRaisesRegex(expected_error, message),
            ):
                OpenAICompatibleClient(purpose="generation").chat(
                    configured_model(), None, [{"role": "user", "content": "test"}]
                )


if __name__ == "__main__":
    unittest.main()
