```tsx
// frontend/app.js
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

// end_of_file
```

```html
// frontend/index.html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#0f172a" />
    <title>LangGraph Multi-Agent Chat</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ctext y='50' font-size='48'%3E%F0%9F%A4%96%3C/text%3E%3C/svg%3E" />
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              brand: {
                50: "#eef4ff",
                100: "#d9e6ff",
                500: "#4f7cff",
                600: "#2f5bff",
                700: "#1e44e0",
              },
            },
          },
        },
      };
    </script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
    <link rel="stylesheet" href="/assets/styles.css" />
  </head>
  <body class="h-[100dvh] bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 antialiased">
    <div class="flex h-[100dvh] flex-col">
      <header class="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div class="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
          <div class="flex items-center gap-2 min-w-0">
            <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
              <span aria-hidden="true">AI</span>
            </div>
            <div class="min-w-0">
              <h1 class="truncate text-sm font-semibold sm:text-base">
                LangGraph Multi-Agent RAG
              </h1>
              <p class="truncate text-[11px] text-slate-500 dark:text-slate-400 sm:text-xs">
                Planner · Product · Policy · Tech · General · DuckDuckGo
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span id="status-dot" class="h-2.5 w-2.5 rounded-full bg-slate-400" aria-hidden="true"></span>
            <button
              id="settings-btn"
              type="button"
              class="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Settings
            </button>
          </div>
        </div>
      </header>

      <main
        id="messages"
        class="flex-1 overflow-y-auto"
        aria-live="polite"
      >
        <div class="mx-auto w-full max-w-3xl px-4 py-6 space-y-4" id="messages-inner">
          <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p class="text-sm leading-relaxed text-slate-700 dark:text-slate-200">
              Welcome! Ask a single question that can span
              <span class="font-medium">products</span>,
              <span class="font-medium">policies</span>,
              <span class="font-medium">tech support</span>, or
              <span class="font-medium">general knowledge</span>. The planner
              will pick one or more specialist agents, each using RAG and
              DuckDuckGo, and a synthesizer will merge the answers.
            </p>
            <div class="mt-3 flex flex-wrap gap-2" id="suggestions">
              <button class="suggestion rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
                What products are available?
              </button>
              <button class="suggestion rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
                What is the return policy?
              </button>
              <button class="suggestion rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
                How do I fix an overheating Dell laptop?
              </button>
              <button class="suggestion rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
                What Dell laptops are available, what is the return policy, and how do I prevent overheating?
              </button>
            </div>
          </div>
        </div>
      </main>

      <footer class="sticky bottom-0 z-20 border-t border-slate-200/70 bg-white/90 backdrop-blur pb-[env(safe-area-inset-bottom)] dark:border-slate-800 dark:bg-slate-900/90">
        <form id="chat-form" class="mx-auto flex max-w-3xl items-end gap-2 px-3 py-3 sm:px-4">
          <label for="chat-input" class="sr-only">Your message</label>
          <textarea
            id="chat-input"
            rows="1"
            placeholder="Ask anything..."
            class="flex-1 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            autocomplete="off"
            autocapitalize="sentences"
            enterkeyhint="send"
          ></textarea>
          <button
            id="send-btn"
            type="submit"
            class="inline-flex h-11 shrink-0 items-center justify-center rounded-2xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
          >
            <span id="send-label">Send</span>
            <svg
              id="send-spinner"
              class="hidden h-5 w-5 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-25"></circle>
              <path d="M4 12a8 8 0 018-8" stroke="currentColor" stroke-width="3" stroke-linecap="round"></path>
            </svg>
          </button>
        </form>
      </footer>
    </div>

    <div
      id="settings-modal"
      class="fixed inset-0 z-30 hidden items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4"
      aria-hidden="true"
    >
      <div
        class="w-full max-w-lg rounded-t-2xl bg-white p-5 shadow-xl dark:bg-slate-900 sm:rounded-2xl"
        role="dialog"
        aria-modal="true"
      >
        <div class="flex items-center justify-between">
          <h2 class="text-base font-semibold">Knowledge base</h2>
          <button
            id="close-settings"
            type="button"
            class="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Upload .txt/.md/.pdf/.docx/.html files. Files are classified by
          filename keyword into product / policy / tech / general collections,
          chunked, embedded, and stored in Chroma.
        </p>

        <form id="upload-form" class="mt-4 space-y-3">
          <input
            id="file-input"
            type="file"
            multiple
            class="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand-600 file:px-3 file:py-2 file:text-white hover:file:bg-brand-700"
          />
          <div class="flex flex-wrap gap-2">
            <button
              type="submit"
              class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Upload & re-index
            </button>
            <button
              id="reindex-btn"
              type="button"
              class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
            >
              Re-index existing docs
            </button>
          </div>
          <div
            id="upload-status"
            class="min-h-[1.25rem] text-xs text-slate-500 dark:text-slate-400"
          ></div>
        </form>
      </div>
    </div>

    <template id="tpl-user-msg">
      <div class="flex justify-end">
        <div class="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm"></div>
      </div>
    </template>

    <template id="tpl-bot-msg">
      <div class="space-y-2">
        <div class="flex items-start gap-2">
          <div class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[11px] font-semibold text-white">
            AI
          </div>
          <div class="min-w-0 flex-1 space-y-2">
            <div class="agent-badges flex flex-wrap gap-1.5"></div>
            <div class="answer prose prose-sm max-w-none rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed shadow-sm dark:prose-invert dark:border-slate-800 dark:bg-slate-900"></div>
            <details class="group rounded-xl border border-slate-200 bg-white/60 px-3 py-2 text-xs dark:border-slate-800 dark:bg-slate-900/60">
              <summary class="cursor-pointer select-none font-medium text-slate-700 dark:text-slate-200">
                Planner / Agent Trace
              </summary>
              <pre class="trace mt-2 whitespace-pre-wrap break-words text-slate-600 dark:text-slate-300"></pre>
            </details>
            <details class="group rounded-xl border border-slate-200 bg-white/60 px-3 py-2 text-xs dark:border-slate-800 dark:bg-slate-900/60">
              <summary class="cursor-pointer select-none font-medium text-slate-700 dark:text-slate-200">
                Specialist Outputs
              </summary>
              <div class="specialists mt-2 space-y-3"></div>
            </details>
          </div>
        </div>
      </div>
    </template>

    <template id="tpl-typing">
      <div class="flex items-start gap-2">
        <div class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[11px] font-semibold text-white">
          AI
        </div>
        <div class="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <span class="typing-dots inline-flex gap-1" aria-label="Thinking">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style="animation-delay: 120ms"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style="animation-delay: 240ms"></span>
          </span>
        </div>
      </div>
    </template>

    <script src="/assets/app.js"></script>
  </body>
</html>

// end_of_file
```

```css
// frontend/styles.css
/* Small style complements that Tailwind doesn't cover inline */

html, body {
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

#chat-input {
  max-height: 40vh;
  min-height: 2.75rem;
  line-height: 1.4;
}

/* Hide scrollbar track but keep scroll in message container */
#messages {
  scroll-behavior: smooth;
  overscroll-behavior: contain;
}

/* Markdown rendering nudges */
.answer pre {
  overflow-x: auto;
  white-space: pre;
  background: rgba(15, 23, 42, 0.04);
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  font-size: 0.8125rem;
}
.dark .answer pre {
  background: rgba(148, 163, 184, 0.1);
}
.answer code {
  font-size: 0.85em;
  padding: 0.1rem 0.35rem;
  border-radius: 0.35rem;
  background: rgba(15, 23, 42, 0.06);
}
.dark .answer code {
  background: rgba(148, 163, 184, 0.15);
}
.answer ul, .answer ol {
  padding-left: 1.25rem;
}
.answer p + p {
  margin-top: 0.65rem;
}

.agent-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.7rem;
  font-weight: 500;
  padding: 0.15rem 0.55rem;
  border-radius: 9999px;
  border: 1px solid transparent;
}
.badge-product   { background: #eef2ff; color: #3730a3; border-color: #c7d2fe; }
.badge-policy    { background: #ecfeff; color: #155e75; border-color: #a5f3fc; }
.badge-tech      { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.badge-general   { background: #f1f5f9; color: #334155; border-color: #e2e8f0; }

@media (prefers-color-scheme: dark) {
  .badge-product { background: rgba(99,102,241,.15); color: #c7d2fe; border-color: rgba(99,102,241,.35); }
  .badge-policy  { background: rgba(14,165,233,.15); color: #bae6fd; border-color: rgba(14,165,233,.35); }
  .badge-tech    { background: rgba(234,179,8,.15);  color: #fde68a; border-color: rgba(234,179,8,.35); }
  .badge-general { background: rgba(148,163,184,.15); color: #e2e8f0; border-color: rgba(148,163,184,.35); }
}

.specialist-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  padding: 0.65rem 0.8rem;
  background: rgba(255,255,255,0.6);
}
.dark .specialist-card {
  border-color: rgb(30 41 59);
  background: rgba(15,23,42,0.5);
}
.specialist-card h4 {
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: 0.35rem;
}
.specialist-card .body {
  font-size: 0.75rem;
  line-height: 1.45;
  color: rgb(51 65 85);
  white-space: pre-wrap;
  word-break: break-word;
}
.dark .specialist-card .body {
  color: rgb(203 213 225);
}

// end_of_file
```
