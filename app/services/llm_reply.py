import json
from typing import Any, Dict, List

from app.services.llm_client import call_llm


class LLMReplyError(RuntimeError):
    pass


def build_reply_messages(user_message: str, selection: Dict[str, Any]) -> List[Dict[str, str]]:
    tool_payload = {
        "tool_name": selection["tool_name"],
        "arguments": selection["arguments"],
        "tool_result": selection["tool_result"],
    }

    return [
        {
            "role": "system",
            "content": (
                "你是电商客服系统里的中文客服助手。"
                "你必须只根据工具结果回复，不能编造工具结果里没有的信息。"
                "如果工具结果显示未找到或失败，要明确告诉用户，并给出下一步建议。"
                "如果工具结果里包含 source 字段，回复末尾要简短标注参考来源。"
                "回复要简洁、自然、礼貌。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户原话：{user_message}\n"
                f"工具执行结果：{json.dumps(tool_payload, ensure_ascii=False)}"
            ),
        },
    ]


def extract_reply_text(llm_response: Dict[str, Any]) -> str:
    try:
        content = llm_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMReplyError("LLM did not return reply content") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMReplyError("LLM returned empty reply content")

    return content.strip()


def generate_llm_reply(user_message: str, selection: Dict[str, Any]) -> str:
    messages = build_reply_messages(user_message, selection)
    response = call_llm(messages)
    return extract_reply_text(response)
