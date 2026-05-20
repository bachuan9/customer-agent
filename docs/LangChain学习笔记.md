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
