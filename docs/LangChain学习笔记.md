# LangChain 学习笔记

## 1. LangChain 是什么

LangChain 是一个帮助开发者搭建 LLM 应用的框架。它不会替代大模型，也不会替代 RAG，本质上是把 LLM 应用里常见的能力封装成标准组件。

```text
Prompt
LLM
Tool
Retriever
Memory
Chain / Runnable
Agent
OutputParser
```

你现在的项目是“原生手写版 Agent”，LangChain 可以看成这些手写模块的框架化版本。

## 2. 和当前项目的概念对照

| LangChain 概念 | 当前项目里的对应代码 | 作用 |
| --- | --- | --- |
| PromptTemplate | `app/services/llm_reply.py` | 组织提示词，把用户问题、工具结果、RAG 结果交给 LLM |
| LLM | `app/services/llm_client.py` | 调用 DeepSeek API |
| Tool | `app/services/tool_registry.py` | 把查询订单、查询物流、检索知识库等能力注册成工具 |
| Retriever | `app/services/tools.py` 里的 `search_knowledge()` | 根据用户问题检索知识库 chunk |
| Memory | `app/storage/database_session.py` + `session_messages` | 保存待确认动作和最近上下文 |
| Chain / Runnable | `app/services/agent.py` | 把识别意图、调用工具、生成回复这些步骤串起来 |
| Agent | `app/services/agent.py` + `app/services/llm_agent.py` | 决定该调用哪个工具，并组织最终回复 |
| OutputParser | `app/services/llm_agent.py` 里的 `extract_first_tool_call()` | 解析 LLM 返回的 tool call |
| Callback / Trace | `web/app.js` 的结构化 Trace + 后端 trace 字段 | 展示 Agent 执行过程、RAG 命中、降级原因 |
| Evaluation | `app/services/agent_evaluation.py` | 自动验证 Agent 行为是否符合预期 |

## 3. 用当前项目理解 LangChain

### Tool

当前项目里，我们自己写了工具注册表：

```text
tool_registry.py
```

它负责：

```text
工具叫什么
工具需要哪些参数
工具会不会修改数据
工具最终调用哪个 Python 函数
```

在 LangChain 里，这类能力一般叫：

```text
Tool
```

### Retriever

当前项目里，RAG 检索入口是：

```text
search_knowledge(query)
```

它负责：

```text
读取知识 chunk
计算关键词分数
计算 embedding 分数
返回最相关的知识片段
```

在 LangChain 里，这类能力通常叫：

```text
Retriever
```

### PromptTemplate

当前项目里，提示词主要在：

```text
llm_reply.py
```

它负责把：

```text
用户原话
工具结果
RAG 命中内容
```

组织成 LLM 能理解的消息。

在 LangChain 里，这类能力通常叫：

```text
PromptTemplate
```

### Chain / Runnable

当前项目里，一次请求会经过：

```text
run_agent_trace()
-> detect_intent()
-> call_tool()
-> format reply
-> return trace
```

这些步骤串起来就是一条链。

在 LangChain 里，这类“把多个步骤串起来”的能力通常叫：

```text
Chain
Runnable
```

### Memory

当前项目里，我们用 `session_messages` 保存 Agent 内部状态，比如：

```text
pending_llm_action
pending_complaint
recent_context
```

这让用户可以这样追问：

```text
查订单 A101
那物流呢
```

在 LangChain 里，这类能力通常叫：

```text
Memory
```

## 4. 为什么不一开始就用 LangChain

因为你现在是学习阶段，先手写底层能理解：

```text
工具怎么注册
参数怎么传递
RAG 怎么检索
Prompt 怎么组织
Trace 怎么返回
Fallback 怎么设计
```

理解这些以后，再学 LangChain 就不会只会“套框架”。

## 5. 后续学习路线

```text
第一步：先理解 LangChain 概念和当前项目的对应关系。
第二步：写一个最小 LangChain demo，只调用 search_knowledge()。
第三步：做一个 LangChain RAG 回复链路，对比原生实现。
第四步：再学习 LangGraph，把 Agent 流程拆成节点和状态图。
```

## 6. 当前环境安装结论

当前项目原来的虚拟环境使用的是：

```text
Python 3.8.0
```

直接安装新版 LangChain 时遇到兼容限制：当前环境只能解析到很老的 `langchain==0.0.27`，而这个旧版 LangChain 使用 Pydantic v1 风格，和项目当前的 `pydantic==2.7.4` 不兼容。

因此项目已新增 Python 3.11 环境：

```text
.venv311
Python 3.11.9
```

当前已安装的 LangChain 标准依赖：

```text
langchain==1.3.1
langchain-core==1.4.0
langchain-community==0.4.1
langchain-text-splitters==1.1.2
langgraph==1.2.0
```

以后运行 LangChain 相关代码时，建议使用：

```powershell
.\.venv311\Scripts\python.exe
```

## 7. 面试时可以这样说

```text
我先用原生 Python 实现了客服 Agent 的工具注册、RAG、Memory、Trace 和 Evaluation，
这样能理解底层链路；后续再引入 LangChain，是为了把 Prompt、Tool、Retriever、Memory 和 Chain 框架化，
并对比原生实现和框架实现的优缺点。
```

## 8. LangChain RAG 小闭环学习笔记

这次新增的是一个独立的 LangChain RAG 学习入口，不替换原来的客服 Agent 主流程。

### 8.1 新增链路

```text
POST /langchain/rag
-> app/api/routes.py
-> run_langchain_rag_agent(question)
-> search_knowledge(question)
-> PromptTemplate
-> RunnableLambda
-> 返回 reply + trace + knowledge_result
```

这条链路的意义是：先让项目真正用上 LangChain 的编排能力，再逐步把真实 LLM、Tool、Memory、LangGraph 接进来。

### 8.2 Prompt 是什么意思

Prompt 可以理解成“给大模型看的任务说明书”。

普通人问客服时，只会说：

```text
我的订单 A101 48 小时了，怎么还没发货？
```

但是大模型需要更清楚的上下文，例如：

```text
你是电商客服助手。
请只根据知识库回答，不要编造。
用户问题是：我的订单 A101 48 小时了，怎么还没发货？
知识库检索结果是：物流超过 48 小时未更新，可以联系客服核实。
请生成自然、礼貌、简洁的中文客服回复。
```

这整段“任务说明 + 用户问题 + 参考资料 + 输出要求”，就叫 Prompt。

### 8.3 PromptTemplate 是什么

PromptTemplate 是 LangChain 提供的“提示词模板”。

它的作用不是直接回答用户，而是先准备一个固定格式：

```text
用户问题：
{question}

知识库片段：
{knowledge_text}

参考来源：
{sources_text}
```

运行时再把真实数据填进去。

在当前项目里，`question` 来自接口请求，`knowledge_text` 和 `sources_text` 来自 `search_knowledge(question)` 的检索结果。

### 8.4 RunnableLambda 是什么

RunnableLambda 可以理解成“把一个普通 Python 函数接进 LangChain 链路”。

当前项目里用了两个 RunnableLambda：

```text
prompt_value_to_text
build_customer_reply
```

`prompt_value_to_text` 负责把 PromptTemplate 生成的对象转成普通字符串。

`build_customer_reply` 负责根据知识库命中结果生成客服回复。

### 8.5 为什么这一步还没有直接调用真实 LLM

这一步的目标是先跑通 LangChain 编排方式：

```text
RAG 检索 -> PromptTemplate -> RunnableLambda -> 结构化返回
```

这样做更安全，因为不会影响原来的 `/chat` 主流程，也不会因为 LLM 网络、Key、余额、模型返回不稳定导致测试失败。

下一步可以继续升级成：

```text
RAG 检索 -> PromptTemplate -> DeepSeek / LLM -> 自然客服回复
```

到那一步，LangChain 就不只是“组织流程”，还会真正参与大模型回复生成。

### 8.6 当前代码位置

如果 IDE 支持 `文件路径:行号` 跳转，可以直接搜索或点击下面这些位置：

```text
app/services/langchain_rag_agent.py:9
app/services/langchain_rag_agent.py:43
app/services/langchain_rag_agent.py:62
app/services/langchain_rag_agent.py:96
app/services/langchain_rag_agent.py:102
app/models/schemas.py:100
app/api/routes.py:631
tests/test_langchain_rag_agent.py:1
```

## 9. LangChain RAG 接入真实 LLM 与降级机制

这一步把上一节的 LangChain RAG 小闭环升级成了“可选调用真实 LLM”的版本。

### 9.1 升级后的链路

```text
POST /langchain/rag
-> run_langchain_rag_agent(question)
-> search_knowledge(question)
-> PromptTemplate 生成 prompt_text
-> 如果 RAG 命中，尝试调用 DeepSeek / LLM
-> 如果 LLM 成功，返回 LLM 生成的自然客服回复
-> 如果 LLM 失败，自动降级为模板回复
-> 返回 reply + trace + knowledge_result
```

### 9.2 为什么要做 fallback

LLM 调用可能因为这些原因失败：

```text
没有开启 LLM
没有配置 API Key
网络超时
模型接口报错
模型返回内容格式不对
```

如果没有 fallback，接口会直接失败，用户就拿不到回复。

有 fallback 后，即使 LLM 不可用，系统仍然可以用知识库命中的内容生成一个稳定回复。

### 9.3 trace 字段怎么看

新增 trace 字段：

```text
llm_used: 是否真的调用并使用了 LLM 回复
reply_source: 回复来源
fallback_reason: 降级原因
```

常见情况：

```json
{
  "llm_used": true,
  "reply_source": "langchain_llm_reply",
  "fallback_reason": null
}
```

表示：RAG 命中，并且 LLM 成功生成了回复。

```json
{
  "llm_used": false,
  "reply_source": "langchain_template_fallback",
  "fallback_reason": "LLM is disabled"
}
```

表示：RAG 命中了，但是 LLM 没启用，所以退回模板回复。

```json
{
  "llm_used": false,
  "reply_source": "langchain_template_fallback",
  "fallback_reason": "knowledge_not_found"
}
```

表示：知识库没有命中，所以没有必要调用 LLM，直接给安全回复。

### 9.4 面试时可以怎么说

```text
我在项目里实现了 LangChain RAG 链路：先通过 embedding + keyword hybrid retrieval 检索知识库，再用 PromptTemplate 构造上下文，命中后调用 LLM 生成自然客服回复。如果 LLM 不可用，会自动 fallback 到模板回复，并通过 trace 暴露 llm_used、reply_source 和 fallback_reason，方便调试和观测。
```

## 10. LangChain Tool 封装 search_knowledge

这一步把原来的 `search_knowledge(query)` 封装成了 LangChain 标准工具。

### 10.1 为什么要封装成 Tool

原来项目里已经有自己的工具注册表：

```text
app/services/tool_registry.py
```

它告诉原生 Agent：

```text
工具叫什么
工具需要什么参数
工具会调用哪个 Python 函数
工具返回什么结果
```

LangChain 也有类似机制，叫 Tool。

这次新增：

```text
app/services/langchain_tools.py
```

作用是把现有 RAG 检索函数包装成 LangChain Tool，让 LangChain 链路可以通过标准工具方式调用知识库。

### 10.2 当前 LangChain Tool 链路

```text
run_langchain_rag_agent(question)
-> call_langchain_search_knowledge(question)
-> search_knowledge_tool.invoke({"query": question})
-> run_search_knowledge_tool(query)
-> search_knowledge(query)
-> 返回 RAG 检索结果
```

注意：底层真正检索知识库的仍然是原来的 `search_knowledge(query)`。

LangChain Tool 这一层主要负责“标准化封装”。

### 10.3 SearchKnowledgeInput 是什么

```text
SearchKnowledgeInput
```

它定义了这个工具需要什么参数。

当前只有一个参数：

```text
query: 用户提出的客服问题，用于检索知识库
```

这和 Function Calling 里的参数 schema 很像。

### 10.4 StructuredTool 是什么

`StructuredTool` 是 LangChain 里用来描述结构化工具的类。

它包含：

```text
name: 工具名
description: 工具说明
args_schema: 参数格式
func: 真正执行的 Python 函数
```

当前项目里的工具名是：

```text
search_knowledge
```

工具说明会告诉 Agent：这个工具适合回答退款、退货、物流超时、会员权益、生鲜破损等政策类问题。

### 10.5 面试时可以怎么说

```text
我把项目中已有的 RAG 检索函数 search_knowledge 封装成 LangChain StructuredTool，并定义了参数 schema、工具描述和统一调用入口。这样可以对比原生 Function Calling 工具注册表和 LangChain Tool 的设计方式，也方便后续接入 LangChain Agent 或 LangGraph 节点。
```

## 11. LangChain Retriever 封装知识库检索

这一步把项目已有的知识库检索能力封装成了 LangChain 标准 Retriever。

### 11.1 Retriever 是什么

Retriever 可以理解成“检索器”。

它专门负责：

```text
接收用户问题
-> 去知识库里找相关内容
-> 返回一组 Document
```

Tool 更像“Agent 可以调用的工具”，Retriever 更像“RAG 专用的取资料组件”。

### 11.2 当前项目里的对应关系

原来的 RAG 检索入口是：

```text
search_knowledge(query)
```

它返回的是普通 Python 字典：

```text
found
matches
sources
```

LangChain Retriever 更标准的返回形式是：

```text
List[Document]
```

所以这次新增了：

```text
app/services/langchain_retriever.py
```

### 11.3 Document 是什么

Document 是 LangChain 表示“知识片段”的标准对象。

它主要包含两部分：

```text
page_content: 文档正文
metadata: 来源、标题、分数、命中关键词等附加信息
```

当前项目里，知识库 match 会被转换成 Document：

```text
match["content"] -> Document.page_content
match["source"] -> Document.metadata["source"]
match["title"] -> Document.metadata["title"]
match["score"] -> Document.metadata["score"]
```

### 11.4 当前 Retriever 链路

```text
retrieve_knowledge_documents(query)
-> get_knowledge_retriever()
-> KnowledgeBaseRetriever.invoke(query)
-> _get_relevant_documents(query)
-> search_knowledge(query)
-> matches 转成 Document 列表
```

底层真正做检索的仍然是 `search_knowledge(query)`。

Retriever 这一层的价值是把结果转换成 LangChain 标准格式。

### 11.5 面试时可以怎么说

```text
我将项目中已有的混合检索 RAG 能力封装成 LangChain BaseRetriever，底层复用 search_knowledge 的关键词 + embedding 检索结果，并将命中的知识片段转换为 LangChain Document，保留 source、title、score、keyword_score、embedding_score 等 metadata，方便后续接入标准 RAG Chain、Agent 或 LangGraph 工作流。
```

## 12. Retriever 代码按真实执行顺序阅读

这部分专门解决一个问题：代码在文件里的位置如果不按流程排列，新手很容易看乱。

现在 `app/services/langchain_retriever.py` 已经按真实运行顺序调整为：

```text
retrieve_knowledge_documents(query)
-> get_knowledge_retriever()
-> KnowledgeBaseRetriever.invoke(query)
-> _get_relevant_documents(query)
-> search_knowledge(query)
-> knowledge_match_to_document(match)
-> 返回 List[Document]
```

### 12.1 第一步：外部入口

```python
def retrieve_knowledge_documents(query: str) -> List[Document]:
    retriever = get_knowledge_retriever()
    return retriever.invoke(query)
```

这一步是给外部调用的入口。

参数 `query` 来自用户问题，例如：

```text
物流 48 小时没有更新怎么办
```

它先创建 Retriever，再用 LangChain 标准方法 `invoke(query)` 执行检索。

### 12.2 第二步：创建 Retriever

```python
def get_knowledge_retriever() -> "KnowledgeBaseRetriever":
    return KnowledgeBaseRetriever()
```

这一步负责创建项目自己的知识库检索器。

以后如果 Retriever 需要配置参数，例如 `top_k`、分类过滤、是否启用 embedding，都可以从这里统一调整。

### 12.3 第三步：LangChain 调用自定义检索逻辑

```python
class KnowledgeBaseRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str) -> List[Document]:
        result = search_knowledge(query)
        return [knowledge_match_to_document(match) for match in result.get("matches", [])]
```

`invoke(query)` 是 LangChain 提供的标准调用方式。

当调用 `retriever.invoke(query)` 时，LangChain 会进入我们自己写的 `_get_relevant_documents(query)`。

这里真正做两件事：

```text
用 search_knowledge(query) 检索知识库
把 matches 转成 Document 列表
```

### 12.4 第四步：复用原有 RAG 检索函数

```python
result = search_knowledge(query)
```

这一行复用项目原来的 RAG 能力。

它会做：

```text
读取知识库 chunk
计算关键词分数
计算 embedding 相似度
返回 matches 和 sources
```

返回结果大概是：

```json
{
  "found": true,
  "matches": [
    {
      "content": "物流超过 48 小时未更新，可以联系客服核实。",
      "source": "docs/knowledge/shipping-policy.md",
      "title": "物流超时政策",
      "score": 5.8
    }
  ],
  "sources": ["docs/knowledge/shipping-policy.md"]
}
```

### 12.5 第五步：把 match 转成 Document

```python
def knowledge_match_to_document(match: Dict[str, Any]) -> Document:
    return Document(
        page_content=match.get("content", ""),
        metadata={
            "source": match.get("source"),
            "title": match.get("title"),
            "score": match.get("score"),
            "keyword_score": match.get("keyword_score"),
            "embedding_score": match.get("embedding_score"),
            "matched_keywords": match.get("matched_keywords", []),
            "matched_groups": match.get("matched_groups", []),
            "retrieval_mode": match.get("retrieval_mode"),
        },
    )
```

这一步是格式转换。

```text
match["content"] -> Document.page_content
match["source"] -> Document.metadata["source"]
match["title"] -> Document.metadata["title"]
match["score"] -> Document.metadata["score"]
```

为什么要转换成 Document？

因为 LangChain 的标准 RAG 组件更认识 `Document`，不认识我们自己定义的 `matches` 字典格式。

### 12.6 最终返回

最终返回的是：

```text
List[Document]
```

也就是：

```python
[
    Document(
        page_content="物流超过 48 小时未更新，可以联系客服核实。",
        metadata={
            "source": "docs/knowledge/shipping-policy.md",
            "title": "物流超时政策",
            "score": 5.8
        }
    )
]
```

### 12.7 一句话复盘

```text
retrieve_knowledge_documents 是入口；
get_knowledge_retriever 创建检索器；
invoke 是 LangChain 的标准调用方式；
_get_relevant_documents 里复用 search_knowledge；
knowledge_match_to_document 把普通字典转成 LangChain Document；
最终返回 List[Document]。
```

## 13. 项目代码阅读顺序约定

为了便于新手理解，后续新增代码尽量按照“真实执行流程”排列。

推荐顺序：

```text
入口函数
-> 流程编排函数
-> 分支处理函数
-> 外部调用函数
-> fallback / 格式化函数
-> 底层转换函数
```

例如 `langchain_rag_agent.py` 当前顺序是：

```text
run_langchain_rag_agent(question)
-> build_langchain_input(question, knowledge_result)
-> build_langchain_rag_chain()
-> build_customer_reply(chain_input)
-> build_langchain_llm_messages(prompt_text)
-> build_template_reply(chain_input)
-> build_knowledge_text(matches)
-> prompt_value_to_text(prompt_value)
```

为什么不是所有函数都能严格入口在最上面？

因为 Python 有些对象在创建时需要依赖前面已经定义好的类或函数。

例如 `langchain_tools.py` 里的 `search_knowledge_tool = StructuredTool.from_function(...)` 创建时，需要先定义：

```text
SearchKnowledgeInput
run_search_knowledge_tool
```

所以代码顺序要同时满足两个原则：

```text
第一：尽量符合真实调用流程，方便阅读
第二：必须符合 Python 运行规则，保证导入时不报错
```
