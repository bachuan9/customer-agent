# Embedding 与 RAG 学习笔记

这份文档整理当前项目中 `embedding` 的学习重点。目标不是先追求复杂模型，而是先看懂 RAG 的核心工程链路：

```text
文字 -> 向量 -> 存库 -> 查询也变向量 -> 计算相似度 -> 找到相关知识 -> Agent 回复
```

## 1. Embedding 是什么

`embedding` 可以先理解成“文字的数字身份证”。

人可以直接理解这句话：

```text
物流 48 小时没有更新
```

但是程序更擅长处理数字，所以我们会把文字变成一串数字：

```text
[0.0, 0.18, 0.0, 0.36, ...]
```

这串数字就是这段文字的 `embedding`。

有了 embedding 以后，系统就可以比较：

```text
用户问题的向量
和
知识库 chunk 的向量
到底有多像
```

相似度越高，说明这段知识越可能适合回答用户问题。

## 2. 当前项目里的 Embedding 位置

当前项目的 embedding 代码主要在：

```text
app/services/tools.py
```

核心函数包括：

```text
normalize_embedding_text(...)
create_local_embedding(...)
serialize_embedding(...)
parse_embedding(...)
cosine_similarity(...)
rebuild_knowledge_index(...)
search_knowledge(...)
```

当前实现是“本地教学版 embedding”，不是外部大模型 embedding API。它的作用是先把完整 RAG 链路跑通，后续可以把 `create_local_embedding(...)` 替换成真实 embedding 模型。

## 3. normalize_embedding_text(...)

代码位置：

```text
app/services/tools.py
```

作用：

```text
把文本做简单清洗，方便后续生成 embedding。
```

当前逻辑：

```python
def normalize_embedding_text(text: str) -> str:
    return text.lower().replace(" ", "")
```

参数：

```text
text：传入的一段文字，可能是用户问题，也可能是知识库 chunk 内容。
```

返回值：

```text
清洗后的字符串。
```

例子：

```text
"物流 48 小时" -> "物流48小时"
```

为什么这样做：

```text
"48 小时" 和 "48小时" 对业务来说意思一样，去掉空格后更容易比较。
```

## 4. create_local_embedding(...)

作用：

```text
把一段文字转成固定长度的数字向量。
```

当前逻辑：

```python
def create_local_embedding(text: str, dimensions: int = LOCAL_EMBEDDING_DIMENSIONS) -> List[float]:
    vector = [0.0] * dimensions
    normalized_text = normalize_embedding_text(text)
    if not normalized_text:
        return vector

    for char in normalized_text:
        digest = hashlib.md5(char.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % dimensions
        vector[index] += 1.0

    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return vector
    return [round(value / length, 6) for value in vector]
```

参数：

```text
text：要转换成 embedding 的文字。
dimensions：向量长度，默认是 64。
```

返回值：

```text
List[float]，也就是一个数字列表。
```

逐步理解：

```text
vector = [0.0] * dimensions
```

先创建一个长度为 64 的全 0 列表。

```text
normalized_text = normalize_embedding_text(text)
```

先把文本清洗。

```text
for char in normalized_text:
```

逐个字符处理文本。

```text
digest = hashlib.md5(char.encode("utf-8")).hexdigest()
```

给每个字符生成一个稳定的哈希值。

```text
index = int(digest[:8], 16) % dimensions
```

把哈希值转换成 0 到 63 之间的位置。

```text
vector[index] += 1.0
```

这个字符落在哪个位置，就让那个位置加 1。

```text
length = math.sqrt(sum(value * value for value in vector))
```

计算向量长度。

```text
return [round(value / length, 6) for value in vector]
```

归一化，避免长文本天然比短文本分数更高。

## 5. serialize_embedding(...)

作用：

```text
把 Python 数字列表转换成字符串，方便存进 SQLite。
```

代码：

```python
def serialize_embedding(embedding: List[float]) -> str:
    return json.dumps(embedding, ensure_ascii=False)
```

参数：

```text
embedding：create_local_embedding(...) 返回的数字列表。
```

返回值：

```text
JSON 字符串。
```

为什么需要它：

```text
SQLite 不能直接保存 Python 的 List[float]，所以要先转成字符串。
```

## 6. parse_embedding(...)

作用：

```text
从数据库取出 embedding 字符串后，把它转回数字列表。
```

代码：

```python
def parse_embedding(value: Optional[str]) -> List[float]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [float(item) for item in parsed if isinstance(item, (int, float))]
```

参数：

```text
value：数据库 knowledge_chunks.embedding 字段里的字符串。
```

返回值：

```text
List[float]。
```

为什么有这么多判断：

```text
防止数据库里没有值、格式坏了、或者内容不是列表时程序崩掉。
```

## 7. cosine_similarity(...)

作用：

```text
比较两个 embedding 有多像。
```

代码：

```python
def cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right))
    left_length = math.sqrt(sum(a * a for a in left))
    right_length = math.sqrt(sum(b * b for b in right))
    if left_length == 0 or right_length == 0:
        return 0.0
    return dot_product / (left_length * right_length)
```

参数：

```text
left：用户问题的 embedding。
right：某个知识 chunk 的 embedding。
```

返回值：

```text
float，相似度分数。
```

简单理解：

```text
两个向量越像，返回值越高。
两个向量越不像，返回值越低。
```

## 8. rebuild_knowledge_index(...) 里怎么生成 embedding

`rebuild_knowledge_index(...)` 的作用是重建知识索引。

它会做这几件事：

```text
清空旧 knowledge_chunks
-> 读取 Markdown 知识文件
-> 切成 chunk
-> 给每个 chunk 生成 embedding
-> 写入 knowledge_chunks 表
-> 读取后台知识库文章
-> 也生成 embedding 并写入 knowledge_chunks 表
```

关键代码：

```python
embedding=serialize_embedding(create_local_embedding(section))
```

这句用于 Markdown chunk。

含义：

```text
section：一个 Markdown 知识块。
create_local_embedding(section)：把知识块变成数字向量。
serialize_embedding(...)：把数字向量转成字符串。
embedding=...：写入 knowledge_chunks.embedding 字段。
```

另一个关键代码：

```python
embedding=serialize_embedding(create_local_embedding(article_text))
```

这句用于后台知识库文章。

含义：

```text
article_text：文章标题 + 文章内容。
create_local_embedding(article_text)：生成向量。
serialize_embedding(...)：转成字符串。
embedding=...：存进数据库。
```

## 9. search_knowledge(...) 里怎么使用 embedding

`search_knowledge(query)` 是 Agent 的知识检索工具。

参数：

```text
query：用户问题，或者 Agent 传进来的检索问题。
```

来源链路：

```text
web/app.js
-> routes.py 的 /chat
-> agent.py 判断意图
-> call_tool("search_knowledge", {"query": message})
-> tools.py 的 search_knowledge(query)
```

关键代码：

```python
query_embedding = create_local_embedding(query)
```

含义：

```text
把用户问题也转换成 embedding。
```

关键代码：

```python
embedding_score = cosine_similarity(query_embedding, parse_embedding(chunk.get("embedding")))
```

含义：

```text
parse_embedding(chunk.get("embedding"))：把数据库里的 chunk embedding 转回数字列表。
cosine_similarity(...)：比较用户问题和知识 chunk 有多像。
embedding_score：向量相似度分数。
```

关键代码：

```python
combined_score = keyword_score + embedding_score
```

含义：

```text
keyword_score：关键词分数。
embedding_score：向量相似度分数。
combined_score：最终排序分数。
```

当前项目使用的是混合检索：

```text
关键词检索 + embedding 相似度
```

也可以叫：

```text
hybrid retrieval
```

为什么不是纯 embedding：

```text
当前 embedding 是教学版本地实现，不是真实模型 embedding。
关键词分数负责稳定命中，embedding 分数负责辅助排序。
```

## 10. 当前项目完整链路

索引阶段：

```text
Markdown / 后台知识库
-> 切成 chunk
-> create_local_embedding(chunk内容)
-> serialize_embedding(...)
-> insert_knowledge_chunk(...)
-> 存进 knowledge_chunks.embedding
```

检索阶段：

```text
用户问题 query
-> create_local_embedding(query)
-> 读取 knowledge_chunks
-> parse_embedding(chunk.embedding)
-> cosine_similarity(query_embedding, chunk_embedding)
-> 得到 embedding_score
-> 加上 keyword_score
-> 排序返回最相关知识
```

Agent 回复阶段：

```text
search_knowledge 返回 matches
-> Agent 使用命中的知识内容
-> 组织客服回复
-> 前端展示回复和 Trace
```

## 11. 面试怎么讲

可以这样说：

```text
我实现了一个 RAG 检索链路：先把 Markdown 和后台知识库文章切成 chunk，写入 knowledge_chunks 表。每个 chunk 会生成 embedding 并持久化。用户提问时，系统会对 query 生成 embedding，然后和 chunk embedding 做 cosine similarity，同时结合关键词分数做 hybrid retrieval，最后返回最相关的知识片段给 Agent。
```

如果面试官问“你这个是真实 embedding 模型吗”，可以这样回答：

```text
当前项目中先实现了一个本地教学版 embedding，用于验证 RAG 的数据链路、索引结构和相似度排序。后续可以把 create_local_embedding(...) 替换成 OpenAI、DeepSeek 或 bge-m3 等真实 embedding 模型，其他索引和检索流程基本不用大改。
```

## 12. 你应该记住的重点

```text
embedding：文字的数字表示。
chunk：被切小的知识块。
knowledge_chunks：保存可检索知识块和 embedding 的表。
cosine_similarity：计算两个向量有多像。
hybrid retrieval：关键词分数 + embedding 相似度的混合检索。
```

最核心的一句话：

```text
RAG 不是让大模型凭空回答，而是先从知识库找资料，再让 Agent 基于资料回答。
```


## 13. RAG Evaluation 是什么

`RAG Evaluation` 可以理解成 RAG 的“小考试”。

我们先准备几条固定测试问题，然后检查 `search_knowledge(query)` 能不能命中预期知识来源。

```text
物流超时 -> 应该命中 shipping-policy.md
7 天退货 -> 应该命中 return-policy.md
会员积分 -> 应该命中 membership-policy.md
完全无关的问题 -> 应该没有命中
```

这一步调用的核心函数是：

```text
search_knowledge(query)
```

它会返回：

```text
是否命中知识库
命中了哪个知识来源
关键词分数和 embedding 分数
```

为什么这一步重要：RAG 不是只要“能回答”就算完成，还要能稳定地找对资料。评测集就是用固定问题反复检查：切片、embedding provider、混合检索、索引重建有没有正常工作。

面试时可以这样说：

```text
我在项目里给 RAG 做了 evaluation workflow，用固定 case 验证检索是否命中预期知识来源，避免修改 embedding 或检索规则后出现质量退化。
```

## 14. RAG Answer Generation 是什么

前面做的是“检索”：用户问问题后，`search_knowledge(query)` 负责从知识库里找相关资料。

这一步做的是“生成”：如果知识库命中了可靠内容，就把“用户原话 + RAG 命中结果”交给 LLM，让它生成更像真实客服的回复。

```text
用户问题
-> search_knowledge(query)
-> 找到 matches 和 sources
-> generate_rag_llm_reply(message, knowledge_result)
-> LLM 基于知识库内容生成回复
-> 如果 LLM 失败，退回规则模板
```

为什么不直接让 LLM 自己回答：因为客服系统需要可控、可追溯。RAG 先给 LLM 提供知识库依据，LLM 只负责把这些依据组织成自然语言，这样能减少胡编乱造。

面试时可以这样说：

```text
我把 RAG 拆成 retrieval 和 answer generation 两步：先用混合检索找到知识 chunk，再把命中内容传给 LLM 生成客服回复；如果 LLM 调用失败，会降级到规则模板，保证系统可用性。
```

## 15. session memory 多轮上下文补全是什么

多轮上下文补全不是让大模型自己猜，而是后端明确保存上一轮的关键参数。

```text
用户：查订单 A101
Agent：查询订单，并把 order_no=A101 写入 session memory
用户：那物流呢
Agent：发现用户没有提供物流号，于是从 session memory 取出 A101
Agent：调用 query_logistics_by_order(order_no="A101")
Agent：查到 L101 后回复物流状态
```

在这个项目里，`session_messages` 表保存 Agent 内部状态，`recent_context` 用来记录最近订单号和物流号。

为什么这一步重要：真实客服对话里，用户不会每句话都重复完整编号。多轮上下文补全可以让 Agent 更像一个连续对话系统，而不是每轮都从零开始。

面试时可以这样说：

```text
我实现了基于 session memory 的多轮上下文补全能力：Agent 会把最近查询到的订单号和物流号保存到会话记忆里，当用户下一轮省略参数时，后端会自动补全参数并调用对应工具。
```

## 16. Agent Evaluation 是什么

`RAG Evaluation` 主要测试知识库检索是否正确，`Agent Evaluation` 测的是整个 Agent 链路是否按预期工作。

```text
用户输入
-> Agent 识别意图
-> 调用工具
-> 生成回复
-> 返回 trace
-> 评测代码检查 intent、reply、RAG、上下文是否符合预期
```

本项目里的 Agent 评测覆盖了：

```text
单轮订单查询
多轮上下文补全物流
RAG 物流政策检索
订单异常多工具处理
```

为什么评测时默认关闭 LLM：真实 LLM 调用可能超时、波动或返回不稳定格式。Agent Evaluation 先测试确定性的核心链路，保证意图识别、工具调用、RAG 和上下文记忆不回归。

面试时可以这样说：

```text
我给 Agent 设计了自动化 evaluation workflow，覆盖意图识别、工具调用、RAG 命中、多轮上下文和组合工具链路；评测默认关闭 LLM，保证结果稳定可重复，用来防止 Agent 行为回归。
```
