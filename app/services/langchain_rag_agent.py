from typing import Any, Dict, List

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.services.langchain_tools import call_langchain_search_knowledge
from app.services.llm_client import LLMClientError, call_llm
from app.services.llm_reply import LLMReplyError, extract_reply_text


LANGCHAIN_RAG_PROMPT = PromptTemplate.from_template(
    """
你是电商客服知识库助手。

用户问题：
{question}

知识库是否命中：
{found}

知识库片段：
{knowledge_text}

参考来源：
{sources_text}

请基于知识库片段组织客服回复。不要编造知识库没有的信息。
"""
)


def run_langchain_rag_agent(question: str) -> Dict[str, Any]:
    knowledge_result = call_langchain_search_knowledge(question)
    chain_input = build_langchain_input(question, knowledge_result)
    chain = build_langchain_rag_chain()
    chain_result = chain.invoke(chain_input)

    return {
        "question": question,
        "reply": chain_result["reply"],
        "trace": {
            **chain_result["trace"],
            "retrieval_mode": "hybrid_keyword_embedding",
        },
        "knowledge_result": knowledge_result,
    }


def build_langchain_input(question: str, knowledge_result: Dict[str, Any]) -> Dict[str, Any]:
    matches = knowledge_result.get("matches", [])
    sources = knowledge_result.get("sources", [])
    return {
        "question": question,
        "found": knowledge_result.get("found", False),
        "knowledge_text": build_knowledge_text(matches),
        "sources_text": "、".join(sources) if sources else "无",
        "matches": matches,
        "sources": sources,
    }


def build_langchain_rag_chain():
    return RunnablePassthrough.assign(
        prompt_text=LANGCHAIN_RAG_PROMPT | RunnableLambda(prompt_value_to_text)
    ) | RunnableLambda(build_customer_reply)


def build_customer_reply(chain_input: Dict[str, Any]) -> Dict[str, Any]:
    found = chain_input.get("found", False)
    sources = chain_input.get("sources", [])
    llm_used = False
    fallback_reason = None
    reply_source = "langchain_template_fallback"

    if found:
        try:
            messages = build_langchain_llm_messages(chain_input.get("prompt_text", ""))
            llm_response = call_llm(messages)
            reply = extract_reply_text(llm_response)
            llm_used = True
            reply_source = "langchain_llm_reply"
        except (LLMClientError, LLMReplyError) as exc:
            fallback_reason = str(exc)
            reply = build_template_reply(chain_input)
    else:
        fallback_reason = "knowledge_not_found"
        reply = build_template_reply(chain_input)

    return {
        "reply": reply,
        "trace": {
            "framework": "langchain",
            "chain": "PromptTemplate -> LLM/RunnableLambda",
            "rag_found": found,
            "llm_used": llm_used,
            "reply_source": reply_source,
            "fallback_reason": fallback_reason,
            "sources": sources,
            "prompt_preview": chain_input.get("prompt_text", "")[:300],
        },
    }


def build_langchain_llm_messages(prompt_text: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是电商客服系统里的中文客服助手。"
                "你必须只根据用户问题和知识库片段回答，不要编造知识库没有的信息。"
                "如果知识库没有命中，要明确说明暂时没有可靠政策依据，并建议转人工确认。"
                "回复要自然、礼貌、简洁，像真实客服。"
            ),
        },
        {
            "role": "user",
            "content": prompt_text,
        },
    ]


def build_template_reply(chain_input: Dict[str, Any]) -> str:
    found = chain_input.get("found", False)
    matches = chain_input.get("matches", [])
    sources = chain_input.get("sources", [])

    if not found or not matches:
        return (
            "我暂时没有在知识库里找到可靠政策依据。"
            "为了避免误导用户，建议转人工客服或主管进一步确认。"
        )

    top_match = matches[0]
    content = top_match.get("content", "").strip()
    source_text = "、".join(sources)
    return (
        "我帮您查到了相关政策："
        f"{content}\n\n"
        "如果用户还需要继续处理，可以根据这个政策结论继续安抚用户，"
        "并视情况创建投诉或升级给客服主管。"
        f"\n参考来源：{source_text}"
    )


def build_knowledge_text(matches: List[Dict[str, Any]]) -> str:
    if not matches:
        return "未检索到可用知识库片段。"

    sections = []
    for index, match in enumerate(matches[:3], start=1):
        title = match.get("title") or "未命名知识"
        content = match.get("content") or ""
        source = match.get("source") or "未知来源"
        sections.append(f"{index}. {title}\n来源：{source}\n内容：{content}")
    return "\n\n".join(sections)


def prompt_value_to_text(prompt_value: Any) -> str:
    if hasattr(prompt_value, "to_string"):
        return prompt_value.to_string()
    return str(prompt_value)
