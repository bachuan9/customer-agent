// 1. 页面元素：从 HTML 里拿到后面要操作的按钮、输入框、聊天区域。
const chatBody = document.getElementById("chatBody");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const userIdInput = document.getElementById("userId");
const agentNameInput = document.getElementById("agentName");
const roleInput = document.getElementById("role");
const loginForm = document.getElementById("loginForm");
const loginUsernameInput = document.getElementById("loginUsername");
const loginPasswordInput = document.getElementById("loginPassword");
const loginBtn = document.getElementById("loginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const loginStatus = document.getElementById("loginStatus");
const statusInput = document.getElementById("status");
const complaintsBtn = document.getElementById("complaintsBtn");
const managerQueueBtn = document.getElementById("managerQueueBtn");
const followUpQueueBtn = document.getElementById("followUpQueueBtn");
const ordersBtn = document.getElementById("ordersBtn");
const logisticsBtn = document.getElementById("logisticsBtn");
const chatSessionsBtn = document.getElementById("chatSessionsBtn");
const knowledgeBtn = document.getElementById("knowledgeBtn");
const toolLogsBtn = document.getElementById("toolLogsBtn");
const usersBtn = document.getElementById("usersBtn");
const auditLogsBtn = document.getElementById("auditLogsBtn");
const clearBtn = document.getElementById("clearBtn");
const statsTotal = document.getElementById("statsTotal");
const statsPending = document.getElementById("statsPending");
const statsHighPriority = document.getElementById("statsHighPriority");
const statsStatusText = document.getElementById("statsStatusText");
const statsPendingText = document.getElementById("statsPendingText");
const statsHighText = document.getElementById("statsHighText");
const knowledgeForm = document.getElementById("knowledgeForm");
const knowledgeIdInput = document.getElementById("knowledgeId");
const knowledgeTitleInput = document.getElementById("knowledgeTitle");
const knowledgeTagsInput = document.getElementById("knowledgeTags");
const knowledgeContentInput = document.getElementById("knowledgeContent");
const knowledgeEnabledInput = document.getElementById("knowledgeEnabled");
const knowledgeList = document.getElementById("knowledgeList");
const saveKnowledgeBtn = document.getElementById("saveKnowledgeBtn");
const cancelKnowledgeEditBtn = document.getElementById("cancelKnowledgeEditBtn");
const refreshKnowledgeBtn = document.getElementById("refreshKnowledgeBtn");
const rebuildKnowledgeIndexBtn = document.getElementById("rebuildKnowledgeIndexBtn");
const knowledgeSearchInput = document.getElementById("knowledgeSearch");
const knowledgeTagFilterInput = document.getElementById("knowledgeTagFilter");
const searchKnowledgeBtn = document.getElementById("searchKnowledgeBtn");
const resetKnowledgeFilterBtn = document.getElementById("resetKnowledgeFilterBtn");
const knowledgePermissionHint = document.getElementById("knowledgePermissionHint");
const ragDebugQueryInput = document.getElementById("ragDebugQuery");
const ragDebugBtn = document.getElementById("ragDebugBtn");
const ragEvalBtn = document.getElementById("ragEvalBtn");
const agentEvalBtn = document.getElementById("agentEvalBtn");
const ragDebugResult = document.getElementById("ragDebugResult");
const ragDebugExamples = document.getElementById("ragDebugExamples");
const chips = document.querySelectorAll(".chip");

const API_BASE = "";
const AUTH_TOKEN_KEY = "customerAgentAuthToken";
const RAG_GROUP_LABELS = {
  shipping: "物流配送",
  return: "退货售后",
  membership: "会员权益",
};
const RAG_DEBUG_EXAMPLES = [
  { label: "物流超时", query: "物流超过48小时没更新怎么办" },
  { label: "退货运费", query: "退货运费谁承担" },
  { label: "会员积分", query: "会员积分退款后会扣回吗" },
  { label: "未命中示例", query: "平台支持虚拟币提现吗" },
];
let currentUser = null;

// 2. 基础工具函数：滚动、转义 HTML、更新状态栏。
function scrollToBottom() {
  chatBody.scrollTop = chatBody.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatRagGroupLabels(groups = []) {
  return groups.map((group) => RAG_GROUP_LABELS[group] || group);
}

function renderRagGroupTags(groups = []) {
  if (!groups.length) {
    return '<span class="rag-group-tag">无</span>';
  }

  return groups
    .map((group) => {
      const label = RAG_GROUP_LABELS[group] || group;
      return `<span class="rag-group-tag rag-group-${escapeHtml(group)}">${escapeHtml(label)}</span>`;
    })
    .join("");
}

function renderRagDebugExamples() {
  ragDebugExamples.innerHTML = RAG_DEBUG_EXAMPLES.map(
    (example) => `
      <button class="rag-example-btn" type="button" data-query="${escapeHtml(example.query)}">
        ${escapeHtml(example.label)}
      </button>
    `
  ).join("");
}

function setStatus(text) {
  if (statusInput) {
    statusInput.value = text;
  }
}

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

function buildAuthHeaders(extraHeaders = {}) {
  const token = getAuthToken();
  const headers = { ...extraHeaders };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function applyLoggedInUser(user) {
  currentUser = user;
  userIdInput.value = user.username;
  agentNameInput.value = user.display_name;
  roleInput.value = user.role;
  loginStatus.textContent = `已登录：${user.display_name}（${user.role === "manager" ? "主管" : "普通客服"}）`;
  updateKnowledgePermissionUI();
}

async function loadCurrentUser() {
  const token = getAuthToken();
  if (!token) return;

  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const user = await res.json();
    applyLoggedInUser(user);
  } catch (err) {
    setAuthToken("");
    currentUser = null;
    loginStatus.textContent = "登录已失效，请重新登录。";
    updateKnowledgePermissionUI();
  }
}

async function login(event) {
  event.preventDefault();

  loginBtn.disabled = true;
  loginBtn.textContent = "登录中...";

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: loginUsernameInput.value.trim(),
        password: loginPasswordInput.value,
      }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    setAuthToken(data.token);
    applyLoggedInUser(data.user);
    await loadChatHistory();
    appendBubble("agent", `登录成功：当前身份是 ${data.user.display_name}。`);
  } catch (err) {
    appendBubble("agent", "登录失败，请检查账号或密码。");
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "登录";
  }
}

async function logout() {
  const token = getAuthToken();

  try {
    if (token) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: buildAuthHeaders(),
      });
    }
  } catch (err) {
    appendBubble("agent", "退出请求失败，但本地登录状态已清除。");
  } finally {
    setAuthToken("");
    currentUser = null;
    loginStatus.textContent = "未登录：当前仍使用下方教学角色。";
    updateKnowledgePermissionUI();
    await loadChatHistory();
    appendBubble("agent", "已退出登录，后端 token 已失效。");
  }
}

function updateStatsCards(stats) {
  if (!stats) return;
  if (statsTotal) statsTotal.textContent = stats.total;
  if (statsPending) statsPending.textContent = stats.need_follow_up;
  if (statsHighPriority) statsHighPriority.textContent = stats.manager_processing;
  if (statsStatusText) {
    statsStatusText.textContent = `处理中 ${stats.processing} / 已解决 ${stats.resolved}`;
  }
  if (statsPendingText) {
    statsPendingText.textContent = stats.need_follow_up > 0 ? "请优先处理这些投诉" : "当前没有需要跟进投诉";
  }
  if (statsHighText) {
    statsHighText.textContent = stats.manager_processing > 0 ? "主管有重点工单处理中" : "主管暂无处理中重点工单";
  }
}

async function loadComplaintStats() {
  try {
    const res = await fetch(`${API_BASE}/complaints/stats`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const stats = await res.json();
    updateStatsCards(stats);
  } catch (err) {
    if (statsStatusText) statsStatusText.textContent = "统计加载失败，请确认后端正在运行";
  }
}

// 3. 聊天气泡渲染：把用户消息和 Agent 回复显示到页面上。
function appendBubble(role, text, options = {}) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}${options.typing ? " typing" : ""}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "我" : "客";

  const content = document.createElement("div");
  content.className = "content";
  content.textContent = text;

  bubble.appendChild(avatar);
  bubble.appendChild(content);
  chatBody.appendChild(bubble);
  scrollToBottom();

  return bubble;
}

function appendHtmlBubble(html, role = "agent") {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "我" : "客";

  const content = document.createElement("div");
  content.className = "content";
  content.innerHTML = html;

  bubble.appendChild(avatar);
  bubble.appendChild(content);
  chatBody.appendChild(bubble);
  scrollToBottom();

  return bubble;
}

function setBubbleText(bubble, text) {
  const content = bubble.querySelector(".content");
  if (content) {
    content.textContent = text;
  }
}

function setBubbleHtml(bubble, html) {
  const content = bubble.querySelector(".content");
  if (content) {
    content.innerHTML = html;
  }
}

function renderAgentSteps(steps = []) {
  if (!steps.length) return "";

  const items = steps
    .map((step, index) => `<li><span>${index + 1}</span>${escapeHtml(step)}</li>`)
    .join("");
  return `
    <div class="agent-steps">
      <strong>Agent 执行步骤</strong>
      <ol>${items}</ol>
    </div>
  `;
}

function renderAgentTrace(trace = {}) {
  if (!trace || !Object.keys(trace).length) return "";

  const selection = trace.selection || {};
  const rag = trace.rag || {};
  const replySourceLabels = {
    rule_template: "规则模板回复",
    llm_reply: "LLM 基于工具结果生成",
    rag_llm_reply: "RAG 命中后由 LLM 生成",
    llm_template_fallback: "LLM 失败后使用工具模板",
  };
  const toolName = selection.tool_name || "无";
  const fallback = trace.llm_fallback_error || "无";
  const requiresConfirmation = selection.requires_confirmation ? "是" : "否";
  const llmReplyGenerated = trace.llm_reply_generated ? "是" : "否";
  const replySource = replySourceLabels[trace.reply_source] || trace.reply_source || "unknown";
  const summarizeJson = (value) => {
    if (!value) return "无";
    const text = JSON.stringify(value);
    return text.length > 160 ? `${text.slice(0, 160)}...` : text;
  };
  const rows = [
    ["意图", trace.intent || "unknown"],
    ["执行模式", trace.execution_mode || "unknown"],
    ["回复来源", replySource],
    ["LLM是否生成最终回复", llmReplyGenerated],
    ["LLM选择工具", toolName],
    ["是否需要确认", requiresConfirmation],
    ["工具参数", summarizeJson(selection.arguments)],
    ["工具结果摘要", summarizeJson(selection.tool_result)],
    ["RAG是否命中", rag.found ? "是" : "否"],
    ["RAG来源", rag.sources?.length ? rag.sources.join("，") : "无"],
    ["RAG最高分", rag.top_score ?? "无"],
    ["RAG检索模式", rag.retrieval_mode || "无"],
    ["关键词分数", rag.keyword_score ?? "无"],
    ["Embedding分数", rag.embedding_score ?? "无"],
    ["命中标题", rag.top_title || "无"],
    ["来源类型", rag.top_source_type || "无"],
    ["RAG命中原因", rag.match_reason || "无"],
    ["LLM降级原因", fallback],
  ];
  const items = rows
    .map(([label, value]) => `<li><span>${escapeHtml(label)}</span>${escapeHtml(String(value))}</li>`)
    .join("");

  return `
    <div class="agent-steps agent-trace">
      <strong>结构化 Trace</strong>
      <ol>${items}</ol>
    </div>
  `;
}

function setBubbleReplyWithSteps(bubble, reply, steps = [], trace = {}) {
  const safeReply = escapeHtml(reply || "（无回复）");
  setBubbleHtml(bubble, `${safeReply}${renderAgentSteps(steps)}${renderAgentTrace(trace)}`);
}

function renderChatHistory(messages = []) {
  chatBody.innerHTML = "";

  if (!messages.length) {
    appendBubble(
      "agent",
      "你好，我是客服助手。你可以输入“查订单 A101”“查物流 L101”，也可以试试“更新订单 A101 shipped”体验二次确认。"
    );
    return;
  }

  messages.forEach((item) => {
    const role = item.sender === "user" ? "user" : "agent";
    const bubble = appendBubble(role, item.message);
    if (role === "agent" && item.steps?.length) {
      setBubbleReplyWithSteps(bubble, item.message, item.steps, item.trace || {});
    }
  });
}

async function loadChatHistory() {
  const userId = userIdInput.value.trim() || "user1";

  try {
    const res = await fetch(`${API_BASE}/chat/history/${encodeURIComponent(userId)}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const messages = await res.json();
    renderChatHistory(messages);
  } catch (err) {
    appendBubble("agent", "聊天历史加载失败，可继续发送新消息。");
  }
}

function renderChatSessions(sessions = []) {
  if (!sessions.length) {
    return "<p class=\"empty-state\">暂无会话记录。</p>";
  }

  const tableHtml = renderTable(
    [
      {
        key: "user_id",
        label: "用户",
        render: (value) =>
          `<button class="link-button chat-session-open-btn" type="button" data-user-id="${escapeHtml(String(value))}">${escapeHtml(String(value))}</button>`,
      },
      { key: "message_count", label: "消息数" },
      {
        key: "needs_reply",
        label: "状态",
        render: (value) => (value ? "待回复" : "已回复"),
      },
      {
        key: "last_sender",
        label: "最后发送方",
        render: (value) => (value === "user" ? "用户" : "Agent"),
      },
      { key: "last_message", label: "最后消息" },
      { key: "last_message_at", label: "最后时间" },
      {
        key: "user_id",
        label: "操作",
        render: (value) =>
          `<button class="link-button chat-session-reply-btn" type="button" data-user-id="${escapeHtml(String(value))}">回复</button>`,
      },
    ],
    sessions
  );

  return `
    ${tableHtml}
    <form class="manual-reply-form">
      <input name="user_id" type="hidden" />
      <textarea name="message" rows="3" placeholder="先点击某个会话的“回复”，再输入人工客服回复内容。"></textarea>
      <div class="form-actions">
        <button type="submit">发送人工回复</button>
      </div>
      <p class="empty-state">人工回复不会调用 Agent，只会作为客服消息保存到聊天历史。</p>
    </form>
  `;
}

async function loadChatSessions() {
  const loadingBubble = appendBubble("agent", "正在加载会话列表...", { typing: true });

  try {
    const res = await fetch(`${API_BASE}/chat/sessions`, {
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const sessions = await res.json();
    setBubbleHtml(loadingBubble, renderChatSessions(sessions));
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "会话列表加载失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
}

async function submitManualReply(form) {
  const userId = String(form.elements.user_id.value || "").trim();
  const message = String(form.elements.message.value || "").trim();

  if (!userId) {
    appendBubble("agent", "请先在会话列表里点击某个用户的“回复”。");
    return;
  }

  if (!message) {
    appendBubble("agent", "请先输入人工客服回复内容。");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/chat/history/${encodeURIComponent(userId)}/reply`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...buildAuthHeaders(),
      },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    form.reset();
    userIdInput.value = userId;
    appendBubble("agent", `已向 ${userId} 发送人工回复，并保存到聊天历史。`);
    await loadChatHistory();
  } catch (err) {
    appendBubble("agent", "人工回复发送失败，请确认后端服务和登录权限。");
  }
}

// 4. 表格渲染：把订单、物流、投诉列表渲染成 HTML 表格。
function renderTable(columns, rows) {
  const head = columns
    .map((col) => `<th>${escapeHtml(typeof col === "string" ? col : col.label)}</th>`)
    .join("");
  const body = rows
    .map(
      (row) =>
        `<tr>${columns
          .map((col) => {
            const key = typeof col === "string" ? col : col.key;
            const value = row[key] ?? "";
            if (typeof col === "object" && typeof col.render === "function") {
              return `<td>${col.render(value, row)}</td>`;
            }
            return `<td>${escapeHtml(String(value))}</td>`;
          })
          .join("")}</tr>`
    )
    .join("");

  return `
    <div style="overflow-x:auto;">
      <table>
        <thead><tr>${head}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

// 5. 输入框和投诉操作按钮：把按钮动作转换成 Agent 指令。
function setSending(isSending) {
  sendBtn.disabled = isSending;
  sendBtn.textContent = isSending ? "发送中..." : "发送请求";
}

function fillMessageInput(message) {
  messageInput.value = message;
  messageInput.focus();
}

function fillComplaintAction(complaintId, action = "assign") {
  const agentName = agentNameInput?.value.trim() || "客服";
  const actionMessages = {
    assign: `分配投诉 ${complaintId} ${agentName}`,
    assignManager: `分配投诉 ${complaintId} 客服主管`,
    managerTake: `主管接单 ${complaintId}`,
    detail: `查看投诉 ${complaintId}`,
    processing: `更新投诉 ${complaintId} processing`,
    resolved: `解决投诉 ${complaintId}`,
    priorityHigh: `设置投诉 ${complaintId} high`,
    priorityMedium: `设置投诉 ${complaintId} medium`,
    priorityLow: `设置投诉 ${complaintId} low`,
    addNote: `备注投诉 ${complaintId} ${agentName}: `,
    listNotes: `查看备注 ${complaintId}`,
    editNote: "修改备注 N-",
    deleteNote: "删除备注 N-",
  };
  const actionLabels = {
    assign: "分配处理人",
    assignManager: "分配给客服主管",
    managerTake: "主管接单",
    detail: "查看详情",
    processing: "改为处理中",
    resolved: "解决投诉",
    priorityHigh: "设为高优先级",
    priorityMedium: "设为中优先级",
    priorityLow: "设为低优先级",
    addNote: "添加备注",
    listNotes: "查看备注",
    editNote: "修改备注",
    deleteNote: "删除备注",
  };
  const draftMessage = actionMessages[action] || actionMessages.assign;
  fillMessageInput(draftMessage);
  appendBubble("agent", `已把投诉 ${complaintId} 的“${actionLabels[action] || actionLabels.assign}”指令填入输入框，你可以修改后点击发送。`);
}

function bindComplaintActionButtons(container) {
  container.querySelectorAll(".complaint-action-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const complaintId = button.dataset.complaintId;
      const action = button.dataset.action;
      if (complaintId) {
        fillComplaintAction(complaintId, action);
      }
    });
  });
}

// 6. 知识库管理：把表单操作转换成 /knowledge 接口请求。
function resetKnowledgeForm() {
  knowledgeIdInput.value = "";
  knowledgeTitleInput.value = "";
  knowledgeTagsInput.value = "";
  knowledgeContentInput.value = "";
  knowledgeEnabledInput.checked = true;
  saveKnowledgeBtn.textContent = "新增知识";
  updateKnowledgePermissionUI();
}

function canManageKnowledge() {
  return currentUser?.role === "manager";
}

function updateKnowledgePermissionUI() {
  const allowed = canManageKnowledge();
  saveKnowledgeBtn.disabled = !allowed;
  cancelKnowledgeEditBtn.disabled = !allowed;
  rebuildKnowledgeIndexBtn.disabled = !allowed;
  knowledgeTitleInput.disabled = !allowed;
  knowledgeTagsInput.disabled = !allowed;
  knowledgeContentInput.disabled = !allowed;
  knowledgeEnabledInput.disabled = !allowed;

  if (knowledgePermissionHint) {
    knowledgePermissionHint.textContent = allowed
      ? "当前为主管账号，可以维护知识库。"
      : "只有主管账号可以维护知识库；普通客服和未登录状态只能查看。";
    knowledgePermissionHint.classList.toggle("allowed", allowed);
  }

  knowledgeList.querySelectorAll(".knowledge-edit-btn, .knowledge-delete-btn").forEach((button) => {
    button.disabled = !allowed;
    button.title = allowed ? "" : "只有主管账号可以维护知识库";
  });
}

function renderKnowledgeList(items) {
  if (!items.length) {
    knowledgeList.innerHTML = '<p class="empty-state">暂无知识库内容，可以先新增一条。</p>';
    return;
  }

  knowledgeList.innerHTML = items
    .map(
      (item) => `
        <article class="knowledge-item">
          <div class="knowledge-item-header">
            <div>
              <strong>${escapeHtml(item.title)}</strong>
              <span>${item.enabled ? "已启用" : "已停用"}</span>
            </div>
            <div class="table-actions">
              <button class="link-button knowledge-edit-btn" data-id="${item.id}" type="button"${canManageKnowledge() ? "" : " disabled"}>编辑</button>
              <button class="link-button danger knowledge-delete-btn" data-id="${item.id}" type="button"${canManageKnowledge() ? "" : " disabled"}>删除</button>
            </div>
          </div>
          <p>${escapeHtml(item.content)}</p>
          <small>标签：${escapeHtml(item.tags || "无")} / 来源：knowledge_articles:${item.id}</small>
        </article>
      `
    )
    .join("");
  updateKnowledgePermissionUI();
}

function buildKnowledgeQueryString() {
  const params = new URLSearchParams();
  const query = knowledgeSearchInput.value.trim();
  const tag = knowledgeTagFilterInput.value.trim();

  if (query) params.set("query", query);
  if (tag) params.set("tag", tag);

  const queryString = params.toString();
  return queryString ? `?${queryString}` : "";
}

function getKnowledgePermissionMessage(status) {
  if (status === 401) {
    return "请先登录主管账号后再维护知识库。";
  }
  if (status === 403) {
    return "当前账号没有权限维护知识库，请切换主管账号。";
  }
  return "知识库操作失败，请检查后端服务或输入内容。";
}

async function loadKnowledgeArticles(showBubble = false) {
  let loadingBubble = null;
  if (showBubble) {
    loadingBubble = appendBubble("agent", "正在刷新知识库列表...");
  }

  try {
    const res = await fetch(`${API_BASE}/knowledge${buildKnowledgeQueryString()}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const items = await res.json();
    renderKnowledgeList(items);
    if (loadingBubble) {
      setBubbleText(loadingBubble, `知识库列表已刷新，共 ${items.length} 条。`);
    }
  } catch (err) {
    knowledgeList.innerHTML = '<p class="empty-state">知识库加载失败，请确认后端正在运行。</p>';
    if (loadingBubble) {
      setBubbleText(loadingBubble, "知识库刷新失败，请确认后端正在运行。");
    }
  }
}

function renderRagDebugResult(result) {
  if (!result.found) {
    ragDebugResult.innerHTML = `
      <p class="empty-state">未命中可靠知识。可以换一个更接近政策内容的问题再试。</p>
    `;
    return;
  }

  ragDebugResult.innerHTML = `
    <div class="rag-debug-summary">
      <strong>命中 ${result.matches.length} 条知识</strong>
      <span>来源：${escapeHtml((result.sources || []).join(", ") || "无")}</span>
    </div>
    ${result.matches
      .map(
        (match) => `
          <article class="rag-debug-item">
            <div class="rag-debug-meta">
              <span>score: ${match.score}</span>
              <span>keyword: ${match.keyword_score ?? "?"}</span>
              <span>embedding: ${match.embedding_score ?? "?"}</span>
              <span>mode: ${escapeHtml(match.retrieval_mode || "?")}</span>
              <span>source: ${escapeHtml(match.source || "无")}</span>
            </div>
            <div class="rag-group-tags">分类：${renderRagGroupTags(match.matched_groups || [])}</div>
            <p class="rag-debug-keywords">关键词：${escapeHtml((match.matched_keywords || []).join(", ") || "无")}</p>
            <p class="rag-debug-reason">命中原因：${escapeHtml(match.match_reason || "暂无命中原因")}</p>
            <pre>${escapeHtml(match.content || "")}</pre>
          </article>
        `
      )
      .join("")}
  `;
}

function renderRagEvaluationResult(result) {
  ragDebugResult.innerHTML = `
    <div class="rag-debug-summary">
      <strong>RAG评测：${result.passed}/${result.total} 通过</strong>
      <span>通过率：${Math.round((result.pass_rate || 0) * 100)}%</span>
    </div>
    ${(result.cases || [])
      .map(
        (item) => `
          <article class="rag-debug-item">
            <div class="rag-debug-meta">
              <span>${item.passed ? "通过" : "失败"}</span>
              <span>期望命中：${item.should_find ? "是" : "否"}</span>
              <span>实际命中：${item.found ? "是" : "否"}</span>
              <span>score: ${item.top_score ?? "无"}</span>
            </div>
            <strong>${escapeHtml(item.name)}</strong>
            <p>问题：${escapeHtml(item.query)}</p>
            <p>期望来源：${escapeHtml(item.expected_source || "无")}</p>
            <p>实际来源：${escapeHtml((item.sources || []).join(", ") || "无")}</p>
          </article>
        `
      )
      .join("")}
  `;
}

function renderAgentEvaluationResult(result) {
  ragDebugResult.innerHTML = `
    <div class="rag-debug-summary">
      <strong>Agent评测：${result.passed}/${result.total} 通过</strong>
      <span>通过率：${Math.round((result.pass_rate || 0) * 100)}%</span>
    </div>
    ${(result.cases || [])
      .map(
        (item) => `
          <article class="rag-debug-item">
            <div class="rag-debug-meta">
              <span>${item.passed ? "通过" : "失败"}</span>
              <span>预期意图：${escapeHtml(item.expected_intent || "无")}</span>
              <span>实际意图：${escapeHtml(item.actual_intent || "无")}</span>
              <span>回复来源：${escapeHtml(item.reply_source || "无")}</span>
              <span>RAG命中：${item.rag_found ? "是" : "否"}</span>
            </div>
            <strong>${escapeHtml(item.name)}</strong>
            <p>输入：${escapeHtml((item.messages || []).join(" -> "))}</p>
            <p>RAG来源：${escapeHtml((item.rag_sources || []).join(", ") || "无")}</p>
            <p>失败原因：${escapeHtml((item.failures || []).join("；") || "无")}</p>
            <pre>${escapeHtml(item.reply || "")}</pre>
          </article>
        `
      )
      .join("")}
  `;
}

async function runRagDebug() {
  const query = ragDebugQueryInput.value.trim();
  if (!query) {
    ragDebugResult.innerHTML = '<p class="empty-state">请先输入一个要调试的问题。</p>';
    return;
  }

  ragDebugBtn.disabled = true;
  ragDebugResult.innerHTML = '<p class="empty-state">正在检索知识库...</p>';

  try {
    const params = new URLSearchParams({ query });
    const res = await fetch(`${API_BASE}/knowledge/search-debug?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const result = await res.json();
    renderRagDebugResult(result);
  } catch (err) {
    ragDebugResult.innerHTML = '<p class="empty-state">RAG 调试失败，请确认后端服务正在运行。</p>';
  } finally {
    ragDebugBtn.disabled = false;
  }
}

async function saveKnowledgeArticle(event) {
  event.preventDefault();

  if (!canManageKnowledge()) {
    appendBubble("agent", "只有主管账号可以维护知识库，请先登录 manager1。");
    return;
  }

  const articleId = knowledgeIdInput.value;
  const payload = {
    title: knowledgeTitleInput.value.trim(),
    content: knowledgeContentInput.value.trim(),
    tags: knowledgeTagsInput.value.trim(),
    enabled: knowledgeEnabledInput.checked,
  };

  if (!payload.title || !payload.content) {
    appendBubble("agent", "知识库标题和内容不能为空。");
    return;
  }

  const path = articleId ? `/knowledge/${articleId}` : "/knowledge";
  const method = articleId ? "PATCH" : "POST";

  saveKnowledgeBtn.disabled = true;
  saveKnowledgeBtn.textContent = articleId ? "保存中..." : "新增中...";

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      appendBubble("agent", getKnowledgePermissionMessage(res.status));
      return;
    }

    resetKnowledgeForm();
    await loadKnowledgeArticles();
    appendBubble("agent", articleId ? "知识库已更新，Agent 下次检索会使用最新内容。" : "知识库已新增，Agent 现在可以检索这条内容。");
  } catch (err) {
    appendBubble("agent", "知识库保存失败，请确认后端服务正在运行。");
  } finally {
    saveKnowledgeBtn.disabled = false;
    saveKnowledgeBtn.textContent = knowledgeIdInput.value ? "保存修改" : "新增知识";
  }
}

async function editKnowledgeArticle(articleId) {
  if (!canManageKnowledge()) {
    appendBubble("agent", "当前账号没有权限编辑知识库，请切换主管账号。");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/knowledge/${articleId}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const article = await res.json();
    knowledgeIdInput.value = article.id;
    knowledgeTitleInput.value = article.title;
    knowledgeTagsInput.value = article.tags || "";
    knowledgeContentInput.value = article.content;
    knowledgeEnabledInput.checked = article.enabled;
    saveKnowledgeBtn.textContent = "保存修改";
    knowledgeTitleInput.focus();
  } catch (err) {
    appendBubble("agent", "读取知识库详情失败。");
  }
}

async function deleteKnowledgeArticle(articleId) {
  if (!canManageKnowledge()) {
    appendBubble("agent", "当前账号没有权限删除知识库，请切换主管账号。");
    return;
  }

  const confirmed = window.confirm("确定删除这条知识库内容吗？");
  if (!confirmed) return;

  try {
    const res = await fetch(`${API_BASE}/knowledge/${articleId}`, {
      method: "DELETE",
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      appendBubble("agent", getKnowledgePermissionMessage(res.status));
      return;
    }
    await loadKnowledgeArticles();
    appendBubble("agent", "知识库内容已删除。");
  } catch (err) {
    appendBubble("agent", "知识库删除失败，请确认后端服务正在运行。");
  }
}

async function runRagEvaluation() {
  ragEvalBtn.disabled = true;
  ragDebugResult.innerHTML = '<p class="empty-state">正在运行 RAG 评测...</p>';
  try {
    const res = await fetch(`${API_BASE}/knowledge/evaluate-rag`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const result = await res.json();
    renderRagEvaluationResult(result);
  } catch (err) {
    ragDebugResult.innerHTML = '<p class="empty-state">RAG 评测失败，请确认后端服务正在运行。</p>';
  } finally {
    ragEvalBtn.disabled = false;
  }
}

async function runAgentEvaluation() {
  agentEvalBtn.disabled = true;
  ragDebugResult.innerHTML = '<p class="empty-state">正在运行 Agent 评测...</p>';
  try {
    const res = await fetch(`${API_BASE}/agent/evaluate`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const result = await res.json();
    renderAgentEvaluationResult(result);
  } catch (err) {
    ragDebugResult.innerHTML = '<p class="empty-state">Agent 评测失败，请确认后端服务正在运行。</p>';
  } finally {
    agentEvalBtn.disabled = false;
  }
}

async function rebuildKnowledgeIndex() {
  if (!canManageKnowledge()) {
    appendBubble("agent", getKnowledgePermissionMessage(403));
    return;
  }

  rebuildKnowledgeIndexBtn.disabled = true;
  rebuildKnowledgeIndexBtn.textContent = "重建中...";
  try {
    const res = await fetch(`${API_BASE}/knowledge/rebuild-index`, {
      method: "POST",
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      appendBubble("agent", getKnowledgePermissionMessage(res.status));
      return;
    }
    const result = await res.json();
    appendBubble(
      "agent",
      `RAG索引已重建：清理旧知识块 ${result.deleted_count} 条，新建知识块 ${result.indexed_count} 条。`
    );
  } catch (err) {
    appendBubble("agent", "RAG索引重建失败，请确认后端服务正在运行。");
  } finally {
    rebuildKnowledgeIndexBtn.disabled = !canManageKnowledge();
    rebuildKnowledgeIndexBtn.textContent = "重建RAG索引";
  }
}

// 7. 发送聊天消息：把输入内容 POST 到 /chat。
async function sendMessage(message) {
  const userId = userIdInput.value.trim() || "user1";
  const role = roleInput?.value || "agent";

  appendBubble("user", message);
  const typingBubble = appendBubble("agent", "正在处理，请稍等...", { typing: true });

  setSending(true);
  setStatus("处理中");

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ user_id: userId, message, role }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    setBubbleReplyWithSteps(typingBubble, data.reply, data.steps || [], data.trace || {});
    typingBubble.classList.remove("typing");
    await loadComplaintStats();
  } catch (err) {
    setBubbleText(typingBubble, "服务请求失败，请确认后端已启动。");
    typingBubble.classList.remove("typing");
  } finally {
    setSending(false);
    setStatus("在线");
  }
}

// 8. 通用列表查询：查询订单列表和物流列表。
async function fetchList(path, emptyText, columns) {
  const loadingBubble = appendBubble("agent", "正在加载列表...", { typing: true });

  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    if (!data.length) {
      setBubbleText(loadingBubble, emptyText);
      loadingBubble.classList.remove("typing");
      return;
    }

    setBubbleHtml(loadingBubble, renderTable(columns, data));
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "查询失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
}

function renderToolLogStats(stats) {
  const failurePercent = Math.round((stats.failure_rate || 0) * 100);
  const errors = stats.errors?.length
    ? stats.errors.map((item) => `${escapeHtml(item.error)}：${item.count}`).join("，")
    : "暂无失败类型";
  const sourceCounts = Object.fromEntries(
    (stats.sources || []).map((item) => [item.source, item.count])
  );
  const llmCount = sourceCounts.llm_agent || 0;
  const confirmedCount = sourceCounts.llm_confirmed_action || 0;
  const deniedCount = sourceCounts.rbac_denied || 0;
  const ruleCount = sourceCounts.rule_agent || 0;
  const unknownCount = sourceCounts.unknown || 0;

  return `
    <div class="log-summary">
      <strong>工具调用健康摘要</strong>
      <p>总调用 ${stats.total} 次，成功 ${stats.success} 次，失败 ${stats.failed} 次，失败率 ${failurePercent}%</p>
      <p>来源统计：LLM ${llmCount} 次，确认执行 ${confirmedCount} 次，权限拒绝 ${deniedCount} 次，规则 Agent ${ruleCount} 次，历史未知 ${unknownCount} 次</p>
      <p>失败类型：${errors}</p>
    </div>
  `;
}

function buildToolLogFilterHtml() {
  return `
    <div class="log-filters">
      <label>
        <span>来源</span>
        <select id="toolLogSourceFilter">
          <option value="">全部来源</option>
          <option value="rule_agent">规则 Agent</option>
          <option value="llm_agent">LLM Agent</option>
          <option value="llm_confirmed_action">LLM 确认执行</option>
          <option value="rbac_denied">权限拒绝</option>
          <option value="unknown">历史未知</option>
        </select>
      </label>
      <label>
        <span>结果</span>
        <select id="toolLogSuccessFilter">
          <option value="">全部结果</option>
          <option value="true">成功</option>
          <option value="false">失败</option>
        </select>
      </label>
      <button class="ghost" id="applyToolLogFilterBtn" type="button">筛选日志</button>
    </div>
  `;
}

function buildToolLogQueryString(source = "", success = "") {
  const params = new URLSearchParams();
  params.set("limit", "20");
  if (source) params.set("source", source);
  if (success) params.set("success", success);
  return `?${params.toString()}`;
}

function renderToolLogTable(logs) {
  return renderTable(
    [
      { key: "id", label: "ID" },
      {
        key: "source",
        label: "来源",
        render: (value) => {
          if (value === "llm_agent") return "LLM Agent";
          if (value === "llm_confirmed_action") return "LLM 确认执行";
          if (value === "rbac_denied") return "权限拒绝";
          return "规则 Agent";
        },
      },
      { key: "tool_name", label: "工具" },
      {
        key: "success",
        label: "结果",
        render: (value) => (value ? "成功" : "失败"),
      },
      {
        key: "arguments",
        label: "参数",
        render: (value) => escapeHtml(JSON.stringify(value)),
      },
      { key: "error", label: "错误" },
      { key: "created_at", label: "时间" },
      {
        key: "id",
        label: "操作",
        render: (value) => `<button class="link-button tool-log-detail-btn" data-log-id="${escapeHtml(String(value))}" type="button">查看详情</button>`,
      },
    ],
    logs
  );
}

function renderToolLogDetail(log) {
  return `
    <div class="tool-log-detail">
      <strong>工具日志详情 #${escapeHtml(String(log.id))}</strong>
      <p>来源：${escapeHtml(log.source)}</p>
      <p>工具：${escapeHtml(log.tool_name)}</p>
      <p>结果：${log.success ? "成功" : "失败"}</p>
      <p>错误：${escapeHtml(log.error || "无")}</p>
      <p>时间：${escapeHtml(log.created_at)}</p>
      <div class="tool-log-detail-actions">
        <button class="ghost copy-tool-log-json-btn" data-log-id="${escapeHtml(String(log.id))}" data-copy-kind="arguments" type="button">复制参数 JSON</button>
        <button class="ghost copy-tool-log-json-btn" data-log-id="${escapeHtml(String(log.id))}" data-copy-kind="result" type="button">复制结果 JSON</button>
      </div>
      <label>参数</label>
      <pre>${escapeHtml(JSON.stringify(log.arguments, null, 2))}</pre>
      <label>返回结果</label>
      <pre>${escapeHtml(JSON.stringify(log.result, null, 2))}</pre>
    </div>
  `;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function bindToolLogCopyButtons(container, log) {
  container.querySelectorAll(".copy-tool-log-json-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const kind = button.dataset.copyKind;
      const data = kind === "result" ? log.result : log.arguments;
      const label = kind === "result" ? "结果" : "参数";

      try {
        await copyTextToClipboard(JSON.stringify(data, null, 2));
        appendBubble("agent", `${label} JSON 已复制到剪贴板。`);
      } catch (err) {
        appendBubble("agent", `${label} JSON 复制失败，请手动选择文本复制。`);
      }
    });
  });
}

function bindToolLogDetailButtons(container, logs) {
  container.querySelectorAll(".tool-log-detail-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const logId = Number(button.dataset.logId);
      const log = logs.find((item) => item.id === logId);
      if (!log) {
        appendBubble("agent", "没有找到这条工具日志详情。");
        return;
      }
      const detailBubble = appendHtmlBubble(renderToolLogDetail(log));
      bindToolLogCopyButtons(detailBubble, log);
    });
  });
}

async function fetchToolLogs() {
  const loadingBubble = appendBubble("agent", "正在加载工具调用日志...", { typing: true });

  try {
    const [statsRes, logsRes] = await Promise.all([
      fetch(`${API_BASE}/tool-logs/stats`),
      fetch(`${API_BASE}/tool-logs${buildToolLogQueryString()}`),
    ]);

    if (!statsRes.ok || !logsRes.ok) {
      throw new Error("tool logs request failed");
    }

    const stats = await statsRes.json();
    const logs = await logsRes.json();

    if (!logs.length) {
      setBubbleHtml(
        loadingBubble,
        `${renderToolLogStats(stats)}${buildToolLogFilterHtml()}<div class="tool-log-table-wrap"><p>暂无工具调用日志。</p></div>`
      );
      bindToolLogFilter(loadingBubble);
      loadingBubble.classList.remove("typing");
      return;
    }

    const tableHtml = renderToolLogTable(logs);

    setBubbleHtml(
      loadingBubble,
      `${renderToolLogStats(stats)}${buildToolLogFilterHtml()}<div class="tool-log-table-wrap">${tableHtml}</div>`
    );
    bindToolLogFilter(loadingBubble);
    bindToolLogDetailButtons(loadingBubble, logs);
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "工具日志加载失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
}

async function fetchFilteredToolLogs(source, success, container) {
  try {
    const res = await fetch(`${API_BASE}/tool-logs${buildToolLogQueryString(source, success)}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const logs = await res.json();
    const oldTable = container.querySelector(".tool-log-table-wrap");
    const tableHtml = logs.length
      ? renderToolLogTable(logs)
      : '<p class="empty-state">没有匹配当前筛选条件的工具日志。</p>';

    if (oldTable) {
      oldTable.innerHTML = tableHtml;
      bindToolLogDetailButtons(container, logs);
    }
  } catch (err) {
    appendBubble("agent", "筛选工具日志失败，请确认后端服务正在运行。");
  }
}

function bindToolLogFilter(container) {
  const sourceSelect = container.querySelector("#toolLogSourceFilter");
  const successSelect = container.querySelector("#toolLogSuccessFilter");
  const applyButton = container.querySelector("#applyToolLogFilterBtn");

  if (!sourceSelect || !successSelect || !applyButton) return;

  applyButton.addEventListener("click", () => {
    fetchFilteredToolLogs(sourceSelect.value, successSelect.value, container);
  });
}

function getAuditActionLabel(action) {
  const labels = {
    "auth.login_success": "登录成功",
    "auth.login_failed": "登录失败",
    "auth.logout": "退出登录",
    "auth.logout_failed": "退出失败",
    "user.create": "新增用户",
    "user.update_role": "修改角色",
    "user.update_active": "启用/禁用用户",
    "user.reset_password": "重置密码",
    "knowledge.create": "新增知识",
    "knowledge.update": "修改知识",
    "knowledge.delete": "删除知识",
  };
  return labels[action] || action;
}

function renderAuditLogStats(stats) {
  const actionText = stats.actions?.length
    ? stats.actions.map((item) => `${getAuditActionLabel(item.action)}：${item.count}`).join(" / ")
    : "暂无操作统计";

  return `
    <div class="log-summary">
      <strong>操作审计摘要</strong>
      <p>总记录 ${stats.total} 条，成功 ${stats.success} 条，失败 ${stats.failed} 条。</p>
      <p>操作分布：${escapeHtml(actionText)}</p>
    </div>
  `;
}

function renderAuditLogTable(logs) {
  return renderTable(
    [
      { key: "id", label: "ID" },
      { key: "actor_username", label: "操作者" },
      {
        key: "action",
        label: "动作",
        render: (value) => getAuditActionLabel(value),
      },
      { key: "target_type", label: "对象类型" },
      { key: "target_id", label: "对象" },
      {
        key: "success",
        label: "结果",
        render: (value) => (value ? "成功" : "失败"),
      },
      {
        key: "detail",
        label: "详情",
        render: (value) => escapeHtml(JSON.stringify(value)),
      },
      { key: "created_at", label: "时间" },
      {
        key: "id",
        label: "操作",
        render: (value) => `<button class="link-button audit-log-detail-btn" data-audit-log-id="${escapeHtml(String(value))}" type="button">查看详情</button>`,
      },
    ],
    logs
  );
}

function renderAuditLogDetail(log) {
  return `
    <div class="audit-log-detail">
      <strong>审计日志详情 #${escapeHtml(String(log.id))}</strong>
      <p>操作者：${escapeHtml(log.actor_username || "未知")}（${escapeHtml(log.actor_role || "未知角色")}）</p>
      <p>动作：${escapeHtml(getAuditActionLabel(log.action))}</p>
      <p>对象：${escapeHtml(log.target_type || "无")} / ${escapeHtml(log.target_id || "无")}</p>
      <p>结果：${log.success ? "成功" : "失败"}</p>
      <p>时间：${escapeHtml(log.created_at)}</p>
      <div class="tool-log-detail-actions">
        <button class="ghost copy-audit-log-json-btn" data-copy-kind="detail" type="button">复制 detail JSON</button>
      </div>
      <label>detail</label>
      <pre>${escapeHtml(JSON.stringify(log.detail, null, 2))}</pre>
    </div>
  `;
}

function bindAuditLogDetailButtons(container, logs) {
  container.querySelectorAll(".audit-log-detail-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const logId = Number(button.dataset.auditLogId);
      const log = logs.find((item) => item.id === logId);
      if (!log) {
        appendBubble("agent", "没有找到这条审计日志详情。");
        return;
      }

      const detailBubble = appendHtmlBubble(renderAuditLogDetail(log));
      const copyButton = detailBubble.querySelector(".copy-audit-log-json-btn");
      if (copyButton) {
        copyButton.addEventListener("click", async () => {
          try {
            await copyTextToClipboard(JSON.stringify(log.detail, null, 2));
            appendBubble("agent", "审计日志 detail JSON 已复制到剪贴板。");
          } catch (err) {
            appendBubble("agent", "审计日志 detail JSON 复制失败，请手动选择文本复制。");
          }
        });
      }
    });
  });
}

function buildAuditLogFilterHtml() {
  return `
    <div class="log-filters">
      <label>
        <span>动作</span>
        <select id="auditActionFilter">
          <option value="">全部动作</option>
          <option value="auth.login_success">登录成功</option>
          <option value="auth.login_failed">登录失败</option>
          <option value="auth.logout">退出登录</option>
          <option value="user.create">新增用户</option>
          <option value="user.update_role">修改角色</option>
          <option value="user.update_active">启用/禁用用户</option>
          <option value="user.reset_password">重置密码</option>
          <option value="knowledge.create">新增知识</option>
          <option value="knowledge.update">修改知识</option>
          <option value="knowledge.delete">删除知识</option>
        </select>
      </label>
      <label>
        <span>结果</span>
        <select id="auditSuccessFilter">
          <option value="">全部结果</option>
          <option value="true">成功</option>
          <option value="false">失败</option>
        </select>
      </label>
      <label>
        <span>操作者</span>
        <input id="auditActorFilter" type="text" placeholder="例如：manager1" />
      </label>
      <button class="ghost" id="applyAuditLogFilterBtn" type="button">筛选审计日志</button>
    </div>
  `;
}

function buildAuditLogQueryString(action = "", success = "", actor = "") {
  const params = new URLSearchParams();
  params.set("limit", "30");
  if (action) params.set("action", action);
  if (success) params.set("success", success);
  if (actor) params.set("actor", actor);
  return `?${params.toString()}`;
}

function getAuditLogErrorMessage(message) {
  if (message.includes("404")) {
    return "审计日志接口不存在，请重启后端服务，让最新 routes.py 生效。";
  }
  if (message.includes("401")) {
    return "登录已失效，请重新登录主管账号。";
  }
  if (message.includes("403")) {
    return "当前账号不是主管，不能查看审计日志。";
  }
  return "审计日志加载失败，请确认后端服务正在运行。";
}

async function fetchAuditLogs() {
  const loadingBubble = appendBubble("agent", "正在加载操作审计日志...", { typing: true });

  try {
    const [statsRes, logsRes] = await Promise.all([
      fetch(`${API_BASE}/audit-logs/stats`, { headers: buildAuthHeaders() }),
      fetch(`${API_BASE}/audit-logs${buildAuditLogQueryString()}`, { headers: buildAuthHeaders() }),
    ]);

    if (!statsRes.ok || !logsRes.ok) {
      throw new Error(`HTTP ${statsRes.status}/${logsRes.status}`);
    }

    const stats = await statsRes.json();
    const logs = await logsRes.json();
    const tableHtml = logs.length
      ? renderAuditLogTable(logs)
      : '<p class="empty-state">暂无操作审计日志。</p>';

    setBubbleHtml(
      loadingBubble,
      `${renderAuditLogStats(stats)}${buildAuditLogFilterHtml()}<div class="tool-log-table-wrap">${tableHtml}</div>`
    );
    bindAuditLogFilter(loadingBubble);
    bindAuditLogDetailButtons(loadingBubble, logs);
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, getAuditLogErrorMessage(err.message));
    loadingBubble.classList.remove("typing");
  }
}

async function fetchFilteredAuditLogs(action, success, actor, container) {
  try {
    const res = await fetch(`${API_BASE}/audit-logs${buildAuditLogQueryString(action, success, actor)}`, {
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const logs = await res.json();
    const oldTable = container.querySelector(".tool-log-table-wrap");
    const tableHtml = logs.length
      ? renderAuditLogTable(logs)
      : '<p class="empty-state">没有匹配当前筛选条件的审计日志。</p>';

    if (oldTable) {
      oldTable.innerHTML = tableHtml;
      bindAuditLogDetailButtons(container, logs);
    }
  } catch (err) {
    appendBubble("agent", getAuditLogErrorMessage(err.message));
  }
}

function bindAuditLogFilter(container) {
  const actionSelect = container.querySelector("#auditActionFilter");
  const successSelect = container.querySelector("#auditSuccessFilter");
  const actorInput = container.querySelector("#auditActorFilter");
  const applyButton = container.querySelector("#applyAuditLogFilterBtn");

  if (!actionSelect || !successSelect || !actorInput || !applyButton) return;

  applyButton.addEventListener("click", () => {
    fetchFilteredAuditLogs(
      actionSelect.value,
      successSelect.value,
      actorInput.value.trim(),
      container
    );
  });
}

// 9. 输入和点击事件：处理发送、回车、快捷话术、动态按钮点击。
// 9. 用户管理：主管可以查看账号、新增账号、调整普通客服/主管角色。
function canManageUsers() {
  return currentUser?.role === "manager";
}

function getUserRoleLabel(role) {
  return role === "manager" ? "主管" : "普通客服";
}

function getUserActiveLabel(isActive) {
  return isActive ? "启用中" : "已禁用";
}

function renderUserManagementPanel(users) {
  const permissionHint = canManageUsers()
    ? "当前是主管账号，可以维护用户。"
    : "只有主管账号可以维护用户，请先登录 manager1。";
  const disabled = canManageUsers() ? "" : " disabled";
  const rowsHtml = users.length
    ? renderTable(
        [
          { key: "username", label: "账号" },
          { key: "display_name", label: "显示名" },
          {
            key: "role",
            label: "角色",
            render: (value) => getUserRoleLabel(value),
          },
          {
            key: "is_active",
            label: "状态",
            render: (value) => getUserActiveLabel(value),
          },
          { key: "created_at", label: "创建时间" },
          { key: "updated_at", label: "更新时间" },
          {
            key: "username",
            label: "操作",
            render: (value, row) => {
              const username = escapeHtml(String(value));
              const nextRole = row.role === "manager" ? "agent" : "manager";
              const nextActive = !row.is_active;
              const activeClass = row.is_active ? " danger" : "";
              return `
                <div class="table-actions">
                  <button class="link-button user-role-btn" data-username="${username}" data-role="${nextRole}" type="button"${disabled}>改为${getUserRoleLabel(nextRole)}</button>
                  <button class="link-button user-active-btn${activeClass}" data-username="${username}" data-active="${String(nextActive)}" type="button"${disabled}>${nextActive ? "启用账号" : "禁用账号"}</button>
                  <button class="link-button user-password-btn" data-username="${username}" type="button"${disabled}>重置密码</button>
                </div>
              `;
            },
          },
        ],
        users
      )
    : '<p class="empty-state">暂无用户。</p>';

  return `
    <div class="user-management-panel">
      <strong>用户管理</strong>
      <p>${permissionHint}</p>
      <form class="user-create-form">
        <input name="username" type="text" placeholder="账号，例如 agent2"${disabled} />
        <input name="display_name" type="text" placeholder="显示名，例如 客服 Carol"${disabled} />
        <input name="password" type="password" placeholder="初始密码"${disabled} />
        <select name="role"${disabled}>
          <option value="agent">普通客服</option>
          <option value="manager">主管</option>
        </select>
        <button type="submit"${disabled}>新增用户</button>
      </form>
      <form class="user-password-form">
        <input name="username" type="text" placeholder="先点击表格里的“重置密码”" readonly${disabled} />
        <input name="password" type="password" placeholder="输入新密码"${disabled} />
        <button type="submit"${disabled}>确认重置密码</button>
      </form>
      <div class="tool-log-table-wrap">${rowsHtml}</div>
    </div>
  `;
}

function getUserErrorMessage(status) {
  if (status === 401) return "请先登录主管账号。";
  if (status === 403) return "当前账号不是主管，不能管理用户。";
  if (status === 409) return "这个用户名已经存在，请换一个账号名。";
  if (status === 400) return "角色只能是普通客服或主管，请检查输入。";
  if (status === 404) return "没有找到这个用户。";
  return "用户管理操作失败，请检查后端服务或输入内容。";
}

async function loadUsers(showLoading = true) {
  const loadingBubble = showLoading
    ? appendBubble("agent", "正在加载用户列表...", { typing: true })
    : null;

  try {
    const res = await fetch(`${API_BASE}/users`, {
      headers: buildAuthHeaders(),
    });
    if (!res.ok) {
      throw new Error(String(res.status));
    }

    const users = await res.json();
    const container = loadingBubble || appendHtmlBubble("");
    setBubbleHtml(container, renderUserManagementPanel(users));
    bindUserManagementPanel(container);
    container.classList.remove("typing");
  } catch (err) {
    const status = Number(err.message);
    const message = getUserErrorMessage(status);
    if (loadingBubble) {
      setBubbleText(loadingBubble, message);
      loadingBubble.classList.remove("typing");
    } else {
      appendBubble("agent", message);
    }
  }
}

async function createUser(form, container) {
  const formData = new FormData(form);
  const payload = {
    username: String(formData.get("username") || "").trim(),
    password: String(formData.get("password") || ""),
    display_name: String(formData.get("display_name") || "").trim(),
    role: String(formData.get("role") || "agent"),
  };

  if (!payload.username || !payload.password || !payload.display_name) {
    appendBubble("agent", "账号、显示名、初始密码都不能为空。");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/users`, {
      method: "POST",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(String(res.status));
    }
    appendBubble("agent", `用户 ${payload.username} 已新增。`);
    await refreshUserPanel(container);
  } catch (err) {
    appendBubble("agent", getUserErrorMessage(Number(err.message)));
  }
}

async function updateUserRoleFromPanel(button, container) {
  const username = button.dataset.username;
  const role = button.dataset.role;

  try {
    const res = await fetch(`${API_BASE}/users/${encodeURIComponent(username)}/role`, {
      method: "PATCH",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      throw new Error(String(res.status));
    }
    appendBubble("agent", `用户 ${username} 已改为${getUserRoleLabel(role)}。`);
    await refreshUserPanel(container);
  } catch (err) {
    appendBubble("agent", getUserErrorMessage(Number(err.message)));
  }
}

async function updateUserActiveFromPanel(button, container) {
  const username = button.dataset.username;
  const isActive = button.dataset.active === "true";

  try {
    const res = await fetch(`${API_BASE}/users/${encodeURIComponent(username)}/active`, {
      method: "PATCH",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ is_active: isActive }),
    });
    if (!res.ok) {
      throw new Error(String(res.status));
    }
    appendBubble("agent", `用户 ${username} 已${isActive ? "启用" : "禁用"}。`);
    await refreshUserPanel(container);
  } catch (err) {
    appendBubble("agent", getUserErrorMessage(Number(err.message)));
  }
}

async function resetUserPasswordFromPanel(form, container) {
  const formData = new FormData(form);
  const username = String(formData.get("username") || "").trim();
  const trimmedPassword = String(formData.get("password") || "").trim();

  if (!username) {
    appendBubble("agent", "请先点击某个用户旁边的“重置密码”。");
    return;
  }

  if (!trimmedPassword) {
    appendBubble("agent", "新密码不能为空。");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/users/${encodeURIComponent(username)}/password`, {
      method: "PATCH",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ password: trimmedPassword }),
    });
    if (!res.ok) {
      throw new Error(String(res.status));
    }
    appendBubble("agent", `用户 ${username} 的密码已重置，请让 TA 使用新密码重新登录。`);
    await refreshUserPanel(container);
  } catch (err) {
    appendBubble("agent", getUserErrorMessage(Number(err.message)));
  }
}

async function refreshUserPanel(container) {
  const res = await fetch(`${API_BASE}/users`, {
    headers: buildAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(String(res.status));
  }
  const users = await res.json();
  setBubbleHtml(container, renderUserManagementPanel(users));
  bindUserManagementPanel(container);
}

function bindUserManagementPanel(container) {
  if (container.dataset.userManagementBound === "true") return;
  container.dataset.userManagementBound = "true";

  container.addEventListener("click", (event) => {
    const roleButton = event.target.closest(".user-role-btn");
    if (roleButton) {
      updateUserRoleFromPanel(roleButton, container);
      return;
    }

    const activeButton = event.target.closest(".user-active-btn");
    if (activeButton) {
      updateUserActiveFromPanel(activeButton, container);
      return;
    }

    const passwordButton = event.target.closest(".user-password-btn");
    if (passwordButton) {
      const passwordForm = container.querySelector(".user-password-form");
      const usernameInput = passwordForm?.querySelector('input[name="username"]');
      const passwordInput = passwordForm?.querySelector('input[name="password"]');
      if (usernameInput && passwordInput) {
        usernameInput.value = passwordButton.dataset.username || "";
        passwordInput.value = "";
        passwordInput.focus();
      }
    }
  });

  container.addEventListener("submit", (event) => {
    const createForm = event.target.closest(".user-create-form");
    if (createForm) {
      event.preventDefault();
      createUser(createForm, container);
      return;
    }

    const passwordForm = event.target.closest(".user-password-form");
    if (passwordForm) {
      event.preventDefault();
      resetUserPasswordFromPanel(passwordForm, container);
    }
  });
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = "";
  sendMessage(message);
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatBody.addEventListener("click", (event) => {
  const sessionButton = event.target.closest(".chat-session-open-btn");
  if (sessionButton) {
    const sessionUserId = sessionButton.dataset.userId;
    if (sessionUserId) {
      userIdInput.value = sessionUserId;
      loadChatHistory();
    }
    return;
  }

  const replyButton = event.target.closest(".chat-session-reply-btn");
  if (replyButton) {
    const sessionUserId = replyButton.dataset.userId;
    const replyForm = chatBody.querySelector(".manual-reply-form");
    if (sessionUserId && replyForm) {
      replyForm.elements.user_id.value = sessionUserId;
      replyForm.elements.message.placeholder = `回复 ${sessionUserId}：请输入人工客服回复内容`;
      replyForm.elements.message.focus();
    }
    return;
  }

  const button = event.target.closest(".complaint-action-btn");
  if (!button) return;

  const complaintId = button.dataset.complaintId;
  if (!complaintId) return;

  fillComplaintAction(complaintId, button.dataset.action);
});

chatBody.addEventListener("submit", (event) => {
  const manualReplyForm = event.target.closest(".manual-reply-form");
  if (!manualReplyForm) return;

  event.preventDefault();
  submitManualReply(manualReplyForm);
});

loginForm.addEventListener("submit", login);

logoutBtn.addEventListener("click", logout);

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const message = chip.dataset.message;
    if (message) sendMessage(message);
  });
});

clearBtn.addEventListener("click", async () => {
  const userId = userIdInput.value.trim() || "user1";

  try {
    const res = await fetch(`${API_BASE}/chat/history/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    chatBody.innerHTML = "";
    appendBubble("agent", "聊天历史已清空，可以继续输入新的问题。");
  } catch (err) {
    appendBubble("agent", "聊天历史清空失败，请确认后端服务正在运行。");
  }
});

chatSessionsBtn.addEventListener("click", loadChatSessions);

// 9. 投诉列表查询：渲染投诉记录和每行操作按钮。
function buildComplaintQuery(params = {}) {
  const queryParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value) queryParams.set(key, value);
  });

  const queryString = queryParams.toString();
  return queryString ? `?${queryString}` : "";
}

function renderComplaintTable(data) {
  return renderTable(
    [
      {
        key: "id",
        label: "编号",
        render: (value) => {
          const id = escapeHtml(String(value));
          return id;
        },
      },
      { key: "user_id", label: "用户ID" },
      { key: "status", label: "状态" },
      { key: "priority", label: "优先级" },
      { key: "follow_up_status", label: "跟进状态" },
      { key: "follow_up_reason", label: "跟进原因" },
      { key: "handler", label: "处理人" },
      { key: "content", label: "内容" },
      { key: "created_at", label: "创建时间" },
      {
        key: "id",
        label: "操作",
        render: (value) => {
          const id = escapeHtml(String(value));
          return `
            <div class="table-actions">
              <button class="link-button complaint-action-btn" data-action="assign" data-complaint-id="${id}" type="button">分配给 Alice</button>
              <button class="link-button complaint-action-btn" data-action="assignManager" data-complaint-id="${id}" type="button">分配给客服主管</button>
              <button class="link-button complaint-action-btn" data-action="managerTake" data-complaint-id="${id}" type="button">主管接单</button>
              <button class="link-button complaint-action-btn" data-action="detail" data-complaint-id="${id}" type="button">查看详情</button>
              <button class="link-button complaint-action-btn" data-action="processing" data-complaint-id="${id}" type="button">改为处理中</button>
              <button class="link-button complaint-action-btn danger" data-action="resolved" data-complaint-id="${id}" type="button">解决投诉</button>
              <button class="link-button complaint-action-btn" data-action="priorityHigh" data-complaint-id="${id}" type="button">高优先级</button>
              <button class="link-button complaint-action-btn" data-action="priorityMedium" data-complaint-id="${id}" type="button">中优先级</button>
              <button class="link-button complaint-action-btn" data-action="priorityLow" data-complaint-id="${id}" type="button">低优先级</button>
              <button class="link-button complaint-action-btn" data-action="addNote" data-complaint-id="${id}" type="button">添加备注</button>
              <button class="link-button complaint-action-btn" data-action="listNotes" data-complaint-id="${id}" type="button">查看备注</button>
              <button class="link-button complaint-action-btn" data-action="editNote" data-complaint-id="${id}" type="button">修改备注</button>
              <button class="link-button complaint-action-btn danger" data-action="deleteNote" data-complaint-id="${id}" type="button">删除备注</button>
            </div>
          `;
        },
      },
    ],
    data.map((item) => ({
      id: item.id,
      user_id: item.user_id,
      status: item.status,
      priority: item.priority,
      follow_up_status: item.follow_up_status || "正常",
      follow_up_reason: item.follow_up_reason || "暂无",
      handler: item.handler || "暂未分配",
      content: item.content,
      created_at: item.created_at,
    }))
  );
}

async function loadComplaints({ params = {}, loadingText = "正在查询投诉记录...", emptyText = "暂无投诉记录。" } = {}) {
  const loadingBubble = appendBubble("agent", loadingText, { typing: true });

  try {
    const res = await fetch(`${API_BASE}/complaints${buildComplaintQuery(params)}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    if (!data.length) {
      setBubbleText(loadingBubble, emptyText);
      loadingBubble.classList.remove("typing");
      return;
    }

    setBubbleHtml(loadingBubble, renderComplaintTable(data));
    bindComplaintActionButtons(loadingBubble);
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "投诉查询失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
}

complaintsBtn.addEventListener("click", async () => {
  const userId = userIdInput.value.trim();
  await loadComplaints({
    params: userId ? { user_id: userId } : {},
  });
});

managerQueueBtn.addEventListener("click", async () => {
  await loadComplaints({
    params: { priority: "high", handler: "客服主管", status: "processing" },
    loadingText: "正在查询主管待处理工单...",
    emptyText: "暂无客服主管正在处理的高优先级投诉。",
  });
});

followUpQueueBtn.addEventListener("click", async () => {
  await loadComplaints({
    params: { follow_up_status: "需要跟进" },
    loadingText: "正在查询需要跟进的投诉...",
    emptyText: "暂无需要跟进的投诉。",
  });
});

// 10. 订单和物流列表查询。
ordersBtn.addEventListener("click", async () => {
  await fetchList("/orders", "暂无订单记录。", [
    { key: "order_no", label: "订单号" },
    { key: "user_id", label: "用户ID" },
    { key: "status", label: "状态" },
    { key: "created_at", label: "创建时间" },
    { key: "updated_at", label: "更新时间" },
  ]);
});

logisticsBtn.addEventListener("click", async () => {
  await fetchList("/logistics", "暂无物流记录。", [
    { key: "tracking_no", label: "物流单号" },
    { key: "order_no", label: "订单号" },
    { key: "status", label: "状态" },
    { key: "created_at", label: "创建时间" },
    { key: "updated_at", label: "更新时间" },
  ]);
});

toolLogsBtn.addEventListener("click", async () => {
  await fetchToolLogs();
});

usersBtn.addEventListener("click", async () => {
  await loadUsers(true);
});

auditLogsBtn.addEventListener("click", async () => {
  await fetchAuditLogs();
});

knowledgeBtn.addEventListener("click", async () => {
  await loadKnowledgeArticles(true);
});

refreshKnowledgeBtn.addEventListener("click", async () => {
  await loadKnowledgeArticles(true);
});

rebuildKnowledgeIndexBtn.addEventListener("click", rebuildKnowledgeIndex);

searchKnowledgeBtn.addEventListener("click", async () => {
  await loadKnowledgeArticles(true);
});

resetKnowledgeFilterBtn.addEventListener("click", async () => {
  knowledgeSearchInput.value = "";
  knowledgeTagFilterInput.value = "";
  await loadKnowledgeArticles(true);
});

ragDebugBtn.addEventListener("click", runRagDebug);
ragEvalBtn.addEventListener("click", runRagEvaluation);
agentEvalBtn.addEventListener("click", runAgentEvaluation);

ragDebugQueryInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runRagDebug();
  }
});

ragDebugExamples.addEventListener("click", (event) => {
  const exampleButton = event.target.closest(".rag-example-btn");
  if (!exampleButton) return;

  ragDebugQueryInput.value = exampleButton.dataset.query;
  runRagDebug();
});

knowledgeForm.addEventListener("submit", saveKnowledgeArticle);

cancelKnowledgeEditBtn.addEventListener("click", () => {
  resetKnowledgeForm();
});

knowledgeList.addEventListener("click", (event) => {
  const editButton = event.target.closest(".knowledge-edit-btn");
  const deleteButton = event.target.closest(".knowledge-delete-btn");

  if (editButton) {
    editKnowledgeArticle(editButton.dataset.id);
    return;
  }

  if (deleteButton) {
    deleteKnowledgeArticle(deleteButton.dataset.id);
  }
});

loadComplaintStats();
loadKnowledgeArticles();
renderRagDebugExamples();
loadCurrentUser().finally(loadChatHistory);
