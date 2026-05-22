import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.core.config import settings


# llm_client.py 阅读地图：
# 1. ensure_llm_ready() 先检查是否允许调用真实 LLM。
# 2. call_llm(...) 组装 DeepSeek 请求，支持普通对话和工具列表。
# 3. 网络、超时、HTTP、JSON 错误统一转成 LLMClientError，方便上层降级。


class LLMClientError(RuntimeError):
    pass


# 1. 调用前检查：没有开启 LLM、没有 key、provider 不支持时，直接阻止调用。
def ensure_llm_ready() -> None:
    if not settings.llm_enabled:
        raise LLMClientError("LLM is disabled")
    if settings.llm_provider != "deepseek":
        raise LLMClientError(f"Unsupported LLM provider: {settings.llm_provider}")
    if not settings.deepseek_api_key:
        raise LLMClientError("DEEPSEEK_API_KEY is not configured")


# 2. 真实 LLM 请求：把 messages/tools 发给 DeepSeek chat completions 接口。
def call_llm(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ensure_llm_ready()

    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
    }
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"LLM HTTP error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"LLM request failed: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise LLMClientError("LLM request timed out") from exc

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise LLMClientError("LLM returned invalid JSON") from exc
