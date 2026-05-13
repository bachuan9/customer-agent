// 1. 页面元素：从 HTML 里拿到后面要操作的按钮、输入框、聊天区域。
const chatBody = document.getElementById("chatBody");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const userIdInput = document.getElementById("userId");
const agentNameInput = document.getElementById("agentName");
const roleInput = document.getElementById("role");
const statusInput = document.getElementById("status");
const complaintsBtn = document.getElementById("complaintsBtn");
const ordersBtn = document.getElementById("ordersBtn");
const logisticsBtn = document.getElementById("logisticsBtn");
const toolLogsBtn = document.getElementById("toolLogsBtn");
const clearBtn = document.getElementById("clearBtn");
const statsTotal = document.getElementById("statsTotal");
const statsPending = document.getElementById("statsPending");
const statsHighPriority = document.getElementById("statsHighPriority");
const statsStatusText = document.getElementById("statsStatusText");
const statsPendingText = document.getElementById("statsPendingText");
const statsHighText = document.getElementById("statsHighText");
const chips = document.querySelectorAll(".chip");

const API_BASE = "";

// 2. 基础工具函数：滚动、转义 HTML、更新状态栏。
function scrollToBottom() {
  chatBody.scrollTop = chatBody.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setStatus(text) {
  if (statusInput) {
    statusInput.value = text;
  }
}

function updateStatsCards(stats) {
  if (!stats) return;
  if (statsTotal) statsTotal.textContent = stats.total;
  if (statsPending) statsPending.textContent = stats.pending;
  if (statsHighPriority) statsHighPriority.textContent = stats.high_priority;
  if (statsStatusText) {
    statsStatusText.textContent = `处理中 ${stats.processing} / 已解决 ${stats.resolved}`;
  }
  if (statsPendingText) {
    statsPendingText.textContent = stats.pending > 0 ? "需要客服优先跟进" : "当前没有待处理投诉";
  }
  if (statsHighText) {
    statsHighText.textContent = stats.high_priority > 0 ? "需要重点关注" : "暂无高优先级投诉";
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

// 6. 发送聊天消息：把输入内容 POST 到 /chat。
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, message, role }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    setBubbleText(typingBubble, data.reply || "（无回复）");
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

// 7. 通用列表查询：查询订单列表和物流列表。
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

async function fetchToolLogs() {
  const loadingBubble = appendBubble("agent", "正在加载工具调用日志...", { typing: true });

  try {
    const [statsRes, logsRes] = await Promise.all([
      fetch(`${API_BASE}/tool-logs/stats`),
      fetch(`${API_BASE}/tool-logs?limit=20`),
    ]);

    if (!statsRes.ok || !logsRes.ok) {
      throw new Error("tool logs request failed");
    }

    const stats = await statsRes.json();
    const logs = await logsRes.json();

    if (!logs.length) {
      setBubbleHtml(loadingBubble, `${renderToolLogStats(stats)}<p>暂无工具调用日志。</p>`);
      loadingBubble.classList.remove("typing");
      return;
    }

    const tableHtml = renderTable(
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
      ],
      logs
    );

    setBubbleHtml(loadingBubble, `${renderToolLogStats(stats)}${tableHtml}`);
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "工具日志加载失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
}

// 8. 输入和点击事件：处理发送、回车、快捷话术、动态按钮点击。
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
  const button = event.target.closest(".complaint-action-btn");
  if (!button) return;

  const complaintId = button.dataset.complaintId;
  if (!complaintId) return;

  fillComplaintAction(complaintId, button.dataset.action);
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const message = chip.dataset.message;
    if (message) sendMessage(message);
  });
});

clearBtn.addEventListener("click", () => {
  chatBody.innerHTML = "";
  appendBubble("agent", "聊天已清空，可以继续输入新的问题。");
});

// 9. 投诉列表查询：渲染投诉记录和每行操作按钮。
complaintsBtn.addEventListener("click", async () => {
  const userId = userIdInput.value.trim();
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  const loadingBubble = appendBubble("agent", "正在查询投诉记录...", { typing: true });

  try {
    const res = await fetch(`${API_BASE}/complaints${query}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    if (!data.length) {
      setBubbleText(loadingBubble, "暂无投诉记录。");
      loadingBubble.classList.remove("typing");
      return;
    }

    setBubbleHtml(
      loadingBubble,
      renderTable(
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
          content: item.content,
          created_at: item.created_at,
        }))
      )
    );
    bindComplaintActionButtons(loadingBubble);
    loadingBubble.classList.remove("typing");
  } catch (err) {
    setBubbleText(loadingBubble, "投诉查询失败，请确认后端服务正在运行。");
    loadingBubble.classList.remove("typing");
  }
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

loadComplaintStats();
