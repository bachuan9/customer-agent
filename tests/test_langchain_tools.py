from app.services.langchain_tools import (
    call_langchain_search_knowledge,
    list_langchain_tools,
    search_knowledge_tool,
)


def test_search_knowledge_tool_has_name_description_and_args():
    assert search_knowledge_tool.name == "search_knowledge"
    assert "客服知识库" in search_knowledge_tool.description

    schema = search_knowledge_tool.args_schema.model_json_schema()
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["type"] == "string"


def test_search_knowledge_tool_invokes_existing_rag_search():
    result = search_knowledge_tool.invoke({"query": "物流 48 小时没有更新怎么办"})

    assert result["found"] is True
    assert result["matches"]
    assert result["sources"]


def test_list_langchain_tools_contains_search_knowledge_tool():
    tools = list_langchain_tools()

    assert search_knowledge_tool in tools
    assert [tool.name for tool in tools] == ["search_knowledge"]


def test_call_langchain_search_knowledge_returns_rag_result():
    result = call_langchain_search_knowledge("退货后多久退款")

    assert result["found"] is True
    assert result["matches"]
    assert result["sources"]
