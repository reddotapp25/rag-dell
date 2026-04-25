(() => {
  const API_BASE = ""; // same-origin when served by FastAPI

  const messagesEl = document.getElementById("messages");
  const messagesInner = document.getElementById("messages-inner");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const sendLabel = document.getElementById("send-label");
  const sendSpinner = document.getElementById("send-spinner");
  const statusDot = document.getElementById("status-dot");
  const suggestions = document.getElementById("suggestions");

  const settingsBtn = document.getElementById("settings-btn");
  const settingsModal = document.getElementById("settings-modal");
  const closeSettings = document.getElementById("close-settings");
  const uploadForm = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const reindexBtn = document.getElementById("reindex-btn");
  const uploadStatus = document.getElementById("upload-status");

  const AGENT_CLASS = {
    product_agent: "badge-product",
    policy_agent: "badge-policy",
    tech_agent: "badge-tech",
    general_agent: "badge-general",
  };
  const AGENT_ICON = {
    product_agent: "📦",
    policy_agent: "📜",
    tech_agent: "🛠️",
    general_agent: "💬",
  };

  function scrollToBottom(smooth = true) {
    requestAnimationFrame(() => {
      messagesEl.scrollTo({
        top: messagesEl.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    });
  }

  function autoresizeTextarea() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, window.innerHeight * 0.4) + "px";
  }
  input.addEventListener("input", autoresizeTextarea);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  function renderMarkdown(text) {
    try {
      const html = window.marked
        ? window.marked.parse(text || "", { breaks: true, gfm: true })
        : (text || "").replace(/</g, "&lt;").replace(/\n/g, "<br>");
      return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
    } catch {
      return (text || "").replace(/</g, "&lt;").replace(/\n/g, "<br>");
    }
  }

  function appendUserMessage(text) {
    const tpl = document.getElementById("tpl-user-msg");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector("div").textContent = text;
    messagesInner.appendChild(node);
    scrollToBottom();
  }

  function appendTyping() {
    const tpl = document.getElementById("tpl-typing");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.typing = "1";
    messagesInner.appendChild(node);
    scrollToBottom();
    return node;
  }

  function appendBotMessage({ response, selected_agents, agent_labels, agent_outputs, debug_log }) {
    const tpl = document.getElementById("tpl-bot-msg");
    const node = tpl.content.firstElementChild.cloneNode(true);

    const badges = node.querySelector(".agent-badges");
    (selected_agents || []).forEach((a) => {
      const badge = document.createElement("span");
      badge.className = `agent-badge ${AGENT_CLASS[a] || "badge-general"}`;
      const label = (agent_labels && agent_labels[a]) || a;
      badge.textContent = `${AGENT_ICON[a] || "🤖"} ${label}`;
      badges.appendChild(badge);
    });
    if (!badges.children.length) badges.remove();

    node.querySelector(".answer").innerHTML = renderMarkdown(response || "");

    const trace = node.querySelector(".trace");
    trace.textContent = debug_log || "(no trace)";

    const specialists = node.querySelector(".specialists");
    const entries = Object.entries(agent_outputs || {});
    if (entries.length === 0) {
      specialists.parentElement.remove();
    } else {
      entries.forEach(([name, out]) => {
        const card = document.createElement("div");
        card.className = "specialist-card";
        const label = (agent_labels && agent_labels[name]) || name;
        card.innerHTML = `<h4>${AGENT_ICON[name] || "🤖"} ${label}</h4><div class="body"></div>`;
        card.querySelector(".body").textContent = out;
        specialists.appendChild(card);
      });
    }

    messagesInner.appendChild(node);
    scrollToBottom();
  }

  function setLoading(loading) {
    sendBtn.disabled = loading;
    input.disabled = loading;
    sendLabel.classList.toggle("hidden", loading);
    sendSpinner.classList.toggle("hidden", !loading);
  }

  async function sendMessage(text) {
    appendUserMessage(text);
    const typingNode = appendTyping();
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json().catch(() => ({}));
      typingNode.remove();

      if (!res.ok) {
        appendBotMessage({
          response: `**Error:** ${data.detail || res.statusText}`,
          selected_agents: [],
          agent_labels: {},
          agent_outputs: {},
          debug_log: "",
        });
      } else {
        appendBotMessage(data);
      }
    } catch (err) {
      typingNode.remove();
      appendBotMessage({
        response: `**Network error:** ${err.message}`,
        selected_agents: [],
        agent_labels: {},
        agent_outputs: {},
        debug_log: "",
      });
    } finally {
      setLoading(false);
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    autoresizeTextarea();
    sendMessage(text);
  });

  suggestions?.addEventListener("click", (e) => {
    const btn = e.target.closest(".suggestion");
    if (!btn) return;
    input.value = btn.textContent.trim();
    autoresizeTextarea();
    input.focus();
  });

  function openSettings() {
    settingsModal.classList.remove("hidden");
    settingsModal.classList.add("flex");
    settingsModal.setAttribute("aria-hidden", "false");
  }
  function closeSettingsModal() {
    settingsModal.classList.add("hidden");
    settingsModal.classList.remove("flex");
    settingsModal.setAttribute("aria-hidden", "true");
  }
  settingsBtn.addEventListener("click", openSettings);
  closeSettings.addEventListener("click", closeSettingsModal);
  settingsModal.addEventListener("click", (e) => {
    if (e.target === settingsModal) closeSettingsModal();
  });

  function summarizeIngest(summary) {
    return Object.entries(summary || {})
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
  }

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const files = fileInput.files;
    if (!files || !files.length) {
      uploadStatus.textContent = "Pick one or more files first.";
      return;
    }
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    uploadStatus.textContent = "Uploading and indexing…";
    try {
      const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      uploadStatus.textContent = `Done. ${summarizeIngest(data.chunks_per_collection)}`;
      fileInput.value = "";
    } catch (err) {
      uploadStatus.textContent = `Error: ${err.message}`;
    }
  });

  reindexBtn.addEventListener("click", async () => {
    uploadStatus.textContent = "Re-indexing…";
    try {
      const res = await fetch(`${API_BASE}/api/ingest?reset=true`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      uploadStatus.textContent = `Re-indexed. ${summarizeIngest(data.chunks_per_collection)}`;
    } catch (err) {
      uploadStatus.textContent = `Error: ${err.message}`;
    }
  });

  async function pollHealth() {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      const data = await res.json();
      const ok = data.status === "ok" && data.has_api_key === "yes";
      statusDot.classList.remove("bg-slate-400", "bg-emerald-500", "bg-amber-500", "bg-rose-500");
      statusDot.classList.add(ok ? "bg-emerald-500" : "bg-amber-500");
      statusDot.title = ok
        ? `Online · ${data.model}`
        : `API reachable, but GROQ_API_KEY is missing`;
    } catch {
      statusDot.classList.remove("bg-slate-400", "bg-emerald-500", "bg-amber-500");
      statusDot.classList.add("bg-rose-500");
      statusDot.title = "Backend unreachable";
    }
  }
  pollHealth();
  setInterval(pollHealth, 30000);

  autoresizeTextarea();
  setTimeout(() => input.focus(), 50);
})();
