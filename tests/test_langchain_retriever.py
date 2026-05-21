from langchain_core.documents import Document

from app.services.langchain_retriever import (
    KnowledgeBaseRetriever,
    get_knowledge_retriever,
    knowledge_match_to_document,
    retrieve_knowledge_documents,
)
from app.services.tools import search_knowledge


def test_knowledge_match_to_document_keeps_content_and_metadata():
    result = search_knowledge("物流 48 小时没有更新怎么办")
    match = result["matches"][0]

    document = knowledge_match_to_document(match)

    assert isinstance(document, Document)
    assert document.page_content == match["content"]
    assert document.metadata["source"] == match["source"]
    assert document.metadata["title"] == match["title"]
    assert document.metadata["retrieval_mode"] == "hybrid_keyword_embedding"


def test_knowledge_base_retriever_returns_langchain_documents():
    retriever = KnowledgeBaseRetriever()

    documents = retriever.invoke("退货后多久退款")

    assert documents
    assert all(isinstance(document, Document) for document in documents)
    assert documents[0].page_content
    assert documents[0].metadata["source"]


def test_get_knowledge_retriever_returns_retriever_instance():
    retriever = get_knowledge_retriever()

    assert isinstance(retriever, KnowledgeBaseRetriever)


def test_retrieve_knowledge_documents_returns_empty_list_when_no_match():
    documents = retrieve_knowledge_documents("平台支持虚拟币提现吗")

    assert documents == []
