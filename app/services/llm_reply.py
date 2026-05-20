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


def build_rag_reply_messages(user_message: str, knowledge_result: Dict[str, Any]) -> List[Dict[str, str]]:
    rag_payload = {
        "found": knowledge_result.get("found", False),
        "query": knowledge_result.get("query", user_message),
        "matches": knowledge_result.get("matches", []),
        "sources": knowledge_result.get("sources", []),
    }

    return [
        {
            "role": "system",
            "content": (
                "你是电商客服系统里的中文客服助手。"
                "你正在根据 RAG 知识库检索结果回复用户。"
                "必须只根据知识库命中内容回答，不要编造知识库没有的信息。"
                "如果知识库没有命中，要说明暂未找到可靠政策，并建议转人工确认。"
                "回复要像真实客服：先安抚，再给结论，再给下一步建议。"
                "回复末尾必须用一句话标注参考来源。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户原话：{user_message}\n"
                f"RAG检索结果：{json.dumps(rag_payload, ensure_ascii=False)}"
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


def generate_rag_llm_reply(user_message: str, knowledge_result: Dict[str, Any]) -> str:
    messages = build_rag_reply_messages(user_message, knowledge_result)
    response = call_llm(messages)
    return extract_reply_text(response)
