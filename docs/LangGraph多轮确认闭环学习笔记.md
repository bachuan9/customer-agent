# LangGraph 多轮确认与创建投诉闭环学习笔记

这一节解决的是一个真实 Agent 项目里很重要的问题：

```text
用户说：物流 48 小时没更新
Agent：先查知识库，再判断这是高风险问题，然后请用户确认是否创建投诉
用户说：确认创建投诉
Agent：读取上一轮保存的待确认动作，真正写入投诉表，并返回投诉编号
```

## 1. 完整流程图

第一轮：用户提出高风险问题。

```text
web/app.js
-> routes.py 的 /langgraph/agent
-> run_langgraph_agent(question, user_id)
-> build_langgraph_workflow()
-> check_pending_confirmation_node
-> select_tool_node
-> call_tool_node
-> assess_risk_node
-> confirm_complaint_node
-> DatabaseSessionStore.append(...)
-> 返回“确认创建投诉”的提示
```

第二轮：用户确认创建投诉。

```text
web/app.js
-> routes.py 的 /langgraph/agent
-> run_langgraph_agent(question, user_id)
-> check_pending_confirmation_node
-> get_pending_confirmation(user_id)
-> create_complaint_node
-> create_complaint(...)
-> db.py 写入 complaints 表
-> set_pending_confirmation(user_id, None)
-> 返回投诉编号
```

## 2. run_langgraph_agent(...)

位置：

```text
app/services/langgraph_agent.py
```

作用：

```text
这是 LangGraph Agent 的入口函数。
路由层调用它，它负责启动整张 LangGraph 流程图。
```

参数从哪里来：

```text
question 来自前端用户输入。
user_id 来自 /langgraph/agent 请求体。
如果前端没有传 user_id，就默认使用 anonymous。
```

参数是什么：

```text
question: str 表示用户这一次说的话。
user_id: str 表示当前用户是谁，用来找到上一轮保存的待确认动作。
```

返回值是什么：

```text
返回一个 dict，里面有 reply、trace、tool_result、created_complaint。
```

返回到哪里：

```text
返回给 routes.py 的 langgraph_agent(...) 接口函数。
再由 FastAPI 返回给前端。
```

为什么这样设计：

```text
因为多轮对话不能只看当前一句话。
用户第二轮说“确认创建投诉”时，系统必须知道上一轮这个用户到底确认的是什么。
所以这里需要 user_id。
```

## 3. check_pending_confirmation_node

作用：

```text
这是 LangGraph 的第一关。
它先检查当前用户有没有上一轮保存的待确认动作。
```

它会做三件事：

```text
1. 用 user_id 去 session_messages 表里找待确认动作。
2. 判断当前 question 是不是“确认创建投诉”。
3. 把判断结果写进 trace，方便前端展示流程。
```

返回值是什么：

```text
pending_confirmation: 找到的待确认动作，可能是 None。
is_confirm_message: 当前消息是不是确认消息。
trace: 当前节点的运行记录。
```

返回到哪里：

```text
返回给 LangGraph。
LangGraph 接着调用 route_after_check_pending_confirmation(...) 决定下一步去哪。
```

## 4. route_after_check_pending_confirmation

作用：

```text
这是条件边。
它不负责干活，只负责判断下一站去哪。
```

判断逻辑：

```text
如果用户说的是“确认创建投诉”，并且系统真的找到了 pending_confirmation：
-> create_complaint

否则：
-> select_tool
```

为什么这样设计：

```text
防止用户一上来就说“确认创建投诉”，系统却在没有上下文的情况下乱创建投诉。
```

## 5. confirm_complaint_node

作用：

```text
第一轮高风险问题到这里时，不直接创建投诉。
它只保存一个“待确认动作”。
```

保存的内容大概是：

```json
{
  "type": "langgraph_pending_confirmation",
  "action": "create_complaint",
  "content": "用户问题：物流 48 小时没有更新怎么办...",
  "priority": "high",
  "handler": "客服主管"
}
```

返回值是什么：

```text
reply: 原来的知识库回复 + “如果需要继续处理，请回复确认创建投诉”。
trace: 标记 requires_confirmation、confirmation_action、pending_saved。
```

返回到哪里：

```text
返回给 LangGraph，然后流程结束。
这一次不会写投诉表。
```

## 6. create_complaint_node

作用：

```text
第二轮用户确认后，这个节点才真正创建投诉。
```

参数从哪里来：

```text
state["user_id"] 来自请求体。
state["pending_confirmation"] 来自上一轮保存到 session_messages 表里的待确认动作。
```

它调用：

```text
create_complaint(
    user_id=state["user_id"],
    content=pending["content"],
    priority=pending.get("priority", "high"),
    handler=pending.get("handler"),
)
```

返回值是什么：

```text
reply: 告诉用户投诉已经创建，并给出投诉编号。
created_complaint: create_complaint(...) 返回的创建结果。
trace: 写入 confirmed_action、complaint_id、pending_cleared。
```

返回到哪里：

```text
返回给 LangGraph，然后 FastAPI 返回给前端。
```

为什么这样设计：

```text
创建投诉是写数据库动作，属于有后果的操作。
所以第一轮只提示确认，第二轮用户明确确认后才执行。
这就是 Agent 项目里常说的 human-in-the-loop 思想，也就是关键动作前保留用户确认。
```

## 7. 面试说法

```text
我在 LangGraph Agent 里实现了一个多轮确认闭环。
第一轮用户提出物流超时、破损、赔付等高风险问题时，Agent 会先通过 RAG 检索知识库并生成回复，然后风险节点识别 high risk，进入确认节点。
确认节点不会直接写数据库，而是把 create_complaint 这个待确认动作保存到 session memory。
第二轮用户回复“确认创建投诉”后，LangGraph 会先检查 session memory，如果存在待确认动作，才调用 create_complaint 工具写入 complaints 表，并返回投诉编号。
这个设计避免了 Agent 自动执行高风险写操作，也让 trace 能清楚展示每个节点的执行过程。
```

## 8. LangGraph 多工具协作

这一节把 LangGraph 从“只会查知识库”升级成“能根据用户问题选择不同工具”。

现在支持三条工具路线：

```text
用户问题里有订单号 A101
-> handle_order_issue
-> 查订单
-> 查订单关联物流
-> 查知识库
-> 生成处理建议
```

```text
用户问题里有物流号 L101
-> handle_logistics_issue
-> 查物流
-> 查知识库
-> 生成处理建议
```

```text
用户问题里没有订单号/物流号，但是像政策问题
-> search_knowledge
-> RAG 检索知识库
-> 返回政策回复
```

### 8.1 select_langgraph_tool(...)

位置：

```text
app/services/langgraph_agent.py
```

作用：

```text
这是 LangGraph 的工具选择函数。
它决定当前用户问题应该走订单工具、物流工具，还是知识库工具。
```

参数从哪里来：

```text
question 来自 run_langgraph_agent(...) 放进 state 的用户原始问题。
select_tool_node 会调用 select_langgraph_tool(state["question"])。
```

参数是什么：

```text
question: str
用户当前输入的一句话，例如：
我的订单 A101 48小时了，怎么还没发货
```

判断顺序：

```text
1. 先用 extract_order_no(question) 找订单号。
2. 如果找到 A101 这类订单号，就选择 handle_order_issue。
3. 如果没有订单号，再用 extract_tracking_no(question) 找物流号。
4. 如果找到 L101 这类物流号，就选择 handle_logistics_issue。
5. 如果都没有，再交给 select_tool_with_llm_fallback(...) 判断是否查知识库。
```

返回值是什么：

```json
{
  "tool_name": "handle_order_issue",
  "arguments": {
    "order_no": "A101",
    "query": "我的订单 A101 48小时了，怎么还没发货"
  },
  "agent_mode": "langgraph_rule_selection",
  "fallback_reason": null
}
```

返回到哪里：

```text
返回给 select_tool_node。
select_tool_node 会把这个 selection 写入 state["selection"]。
```

为什么这样设计：

```text
订单号和物流号是非常明确的业务编号。
这种情况不需要先问大模型，直接用规则识别更稳定、更快、更省钱。
没有明显业务编号时，再交给 LLM/LangChain 判断是否需要查知识库。
```

### 8.2 call_tool_node(...)

作用：

```text
这是 LangGraph 真正调用工具的节点。
select_tool_node 只负责“选工具”，call_tool_node 才负责“执行工具”。
```

参数从哪里来：

```text
它从 state["selection"] 里读取 tool_name 和 arguments。
selection 是 select_tool_node 上一步放进去的。
```

核心判断：

```text
如果 tool_name == "handle_order_issue"
-> 调用 handle_order_issue(order_no, query)

如果 tool_name == "handle_logistics_issue"
-> 调用 handle_logistics_issue(tracking_no, query)

否则
-> 调用 run_langchain_rag_agent(query)
```

返回值是什么：

```text
reply: 给用户看的回复。
trace: 工具调用过程记录。
tool_result: 工具返回的结构化结果。
```

返回到哪里：

```text
返回给 LangGraph 的 state。
下一步 assess_risk_node 会读取 state["tool_result"] 判断是否高风险。
```

### 8.3 handle_order_issue(...)

位置：

```text
app/services/tools.py
```

作用：

```text
这是订单问题的组合工具。
它不是只查订单，而是把订单、物流、知识库组合起来。
```

它内部会做：

```text
query_order(order_no)
-> 查订单状态

query_logistics_by_order(order_no)
-> 查这个订单有没有关联物流

search_knowledge(query)
-> 查知识库政策

build_order_issue_suggestion(...)
-> 生成客服处理建议
```

返回值会包含：

```text
order_no
order_status
tracking_no
logistics_status
knowledge_found
suggest_complaint
agent_suggestion
```

为什么这样设计：

```text
真实客服处理订单问题时，不会只看订单表。
他通常会同时看订单状态、物流状态、平台政策，再决定怎么回复。
所以这是一个“业务组合工具”。
```

### 8.4 handle_logistics_issue(...)

位置：

```text
app/services/tools.py
```

作用：

```text
这是物流问题的组合工具。
它负责查物流状态，并结合知识库给出客服建议。
```

它内部会做：

```text
query_logistics(tracking_no)
-> 查物流单

search_knowledge(query)
-> 查物流相关政策

build_logistics_issue_suggestion(...)
-> 生成客服处理建议
```

返回值会包含：

```text
tracking_no
order_no
logistics_status
knowledge_found
suggest_complaint
agent_suggestion
```

### 8.5 assess_risk_level(question, tool_result)

作用：

```text
判断当前问题是否属于高风险。
```

以前它只看用户文本：

```text
问题里有没有 48小时、超时、投诉、破损、赔付、升级
```

现在它还会看工具结果：

```text
如果 tool_result["suggest_complaint"] == True
-> 直接判定 high
```

为什么这样设计：

```text
有些风险不是只靠用户一句话能判断出来的。
比如订单本身没有物流记录，且知识库命中超时政策，这时工具结果也应该影响风险判断。
这让 Agent 更像一个会结合业务数据做决策的系统。
```

### 8.6 面试说法

```text
我在 LangGraph Agent 中实现了多工具协作。
工具选择节点会先用规则识别订单号和物流号，因为业务编号是确定性强的信号，不需要每次都交给大模型。
如果识别到订单号，会调用 handle_order_issue 组合工具，同时查询订单、关联物流和知识库；如果识别到物流号，会调用 handle_logistics_issue 查询物流和知识库；没有业务编号时再走 LangChain RAG。
工具结果会进入风险评估节点，如果工具判断 suggest_complaint 为 true，就进入高风险确认流程，等待用户确认后再创建投诉。
这个设计把 LLM、规则、业务工具、RAG、LangGraph 状态机串成了一条完整 Agent 工作流。
```
