/* OMAP(R) Admin Dashboard — SPA logic (hash routing + module views) */
"use strict";

/* ---------------- Routing ---------------- */
const ROUTES = {
  "": { view: "home", title: "" },
  "chats": { view: "chats", title: "Chats Review" },
  "tickets-automation": { view: "tickets-automation", title: "Tickets Automation" },
  "osd-imap": { view: "osd-imap", title: "OSD → IMAP" },
  "close-tickets": { view: "close-tickets", title: "Close Tickets" },
};

function route() {
  const slug = location.hash.replace(/^#\/?/, "").replace(/\/$/, "");
  const r = ROUTES[slug] || ROUTES[""];
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${r.view}`).classList.add("active");
  document.body.dataset.view = r.view;
  document.getElementById("crumb-current").textContent = r.title;
  document.title = r.title ? `${r.title} · OMAP® Admin Dashboard` : "OMAP® Admin Dashboard";
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
route();

/* ---------------- Helpers ---------------- */
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("toasts").appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 4000);
}

function setLoading(btn, loading, labelIdle) {
  btn.disabled = loading;
  if (loading) {
    btn.dataset.idle = btn.innerHTML;
    btn.innerHTML = `<span class="spinner" aria-hidden="true"></span> Working…`;
  } else if (btn.dataset.idle) {
    btn.innerHTML = labelIdle || btn.dataset.idle;
  }
}

function skeleton(rows = 5) {
  return `<div class="skeleton" role="status" aria-label="Loading">` +
    Array.from({ length: rows }, () => `<div class="sk-row"></div>`).join("") + `</div>`;
}

function stateBox(title, detail, isError = false) {
  const icon = isError
    ? `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>`
    : `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;
  return `<div class="state-box${isError ? " error" : ""}">${icon}
    <div class="state-title">${esc(title)}</div><div>${esc(detail || "")}</div></div>`;
}

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* not json */ }
    throw new Error(detail);
  }
  return resp.json();
}

function statCard(label, value, kind = "") {
  return `<div class="stat ${kind}"><div class="stat-label">${esc(label)}</div>
    <div class="stat-value">${esc(value)}</div></div>`;
}

function sentimentBadge(s) {
  const v = (s || "N/A").toLowerCase();
  const kind = v.includes("pos") ? "badge-success" : v.includes("neg") ? "badge-danger" : "";
  return `<span class="badge ${kind}">${esc(s || "N/A")}</span>`;
}

function sentimentInfo(s) {
  const v = (s || "").toLowerCase();
  if (v.includes("pos")) return { emoji: "😊", cls: "positive" };
  if (v.includes("neg")) return { emoji: "😟", cls: "negative" };
  return { emoji: "😐", cls: "" };
}

const ICON = {
  calendar: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/></svg>`,
  messages: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  tag: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42Z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>`,
  pin: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`,
  search: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
  files: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/></svg>`,
};

// files_searched items may be Mongo sub-documents (objects) — render as a Python-dict-style string
function formatFileTag(f) {
  if (typeof f === "string") return f;
  if (f && typeof f === "object") {
    const parts = Object.entries(f).map(([k, v]) => `'${k}': ${v === null || v === undefined ? "None" : `'${v}'`}`);
    return `{${parts.join(", ")}}`;
  }
  return String(f ?? "");
}

/* =========================================================== Chats Review */
let md = null;
function renderMarkdown(text) {
  if (!md && window.markdownit) md = window.markdownit({ linkify: true, breaks: true });
  return md ? md.render(String(text ?? "")) : `<p>${esc(text)}</p>`;
}

$("chats-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const org = $("chats-org").value.trim();
  const session = $("chats-session").value.trim();
  const results = $("chats-results");
  const stats = $("chats-stats");
  setLoading($("chats-submit"), true);
  stats.hidden = true;
  results.innerHTML = skeleton(4);
  try {
    const data = await api(`/api/chats/sessions?organization_id=${encodeURIComponent(org)}&session_id=${encodeURIComponent(session)}`);
    const sc = data.sentiment_counts || {};
    stats.innerHTML =
      statCard("Sessions", data.total_sessions) +
      statCard("Positive", sc.Positive || 0, "stat-success") +
      statCard("Neutral", sc.Neutral || 0, "stat-info") +
      statCard("Negative", sc.Negative || 0, "stat-danger");
    stats.hidden = false;

    if (!data.sessions.length) {
      results.innerHTML = stateBox("No sessions found",
        `Organization ${org} has no matching chat sessions${session ? " for that session ID" : ""}.`);
      return;
    }
    results.innerHTML = data.sessions.map((s, i) => {
      const sentiment = sentimentInfo(s.sentiment);
      return `
      <div class="session-card" id="sess-${i}">
        <div class="session-head" role="button" tabindex="0" aria-expanded="false" aria-controls="sess-body-${i}">
          <div class="session-head-top">
            <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
            <span class="session-id">${esc(s.session_id)}</span>
          </div>
          <div class="session-meta">
            <span class="chat-meta-item">${ICON.calendar}${esc(s.created_at)}</span>
            <span class="chat-meta-item">${ICON.messages}${s.message_count} messages</span>
            <span class="chat-meta-item">${ICON.pin}<span class="chat-pill category">${esc(s.category)}</span></span>
            <span class="chat-meta-item">${sentiment.emoji}<span class="chat-pill sentiment ${sentiment.cls}">${esc(s.sentiment)}</span></span>
            <span class="chat-meta-item">${ICON.tag}<span class="chat-pill version">${esc(s.agent_version)}</span></span>
          </div>
        </div>
        <div class="session-body" id="sess-body-${i}">
        <div class="session-body-inner">
          <div class="chat-divider"></div>
          ${s.messages.map(m => `
            <div class="msg ${m.role}">
              <span class="msg-avatar" aria-hidden="true">${m.role === "user"
                ? `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`
                : `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" x2="8" y1="16" y2="16"/><line x1="16" x2="16" y1="16" y2="16"/></svg>`}</span>
              <div class="msg-body">
                <div class="msg-role-line">
                  <span class="msg-role">${m.role === "user" ? "User" : "Assistant"}</span>
                </div>
                <div class="msg-content">${m.role === "assistant" ? renderMarkdown(m.content) : `<p>${esc(m.content)}</p>`}</div>
                <div class="msg-ts">${esc(m.timestamp)}</div>
              </div>
            </div>
            ${m.role === "user" && m.source_page && m.source_page !== "N/A" ? `
              <div class="chat-source-row">${ICON.pin}<span>Source Page:</span><span class="chat-source-badge">${esc(m.source_page)}</span></div>` : ""}
            ${m.role === "assistant" && (m.queries || []).length ? `
              <div class="chat-tags-section">
                <div class="chat-tags-label">${ICON.search} Queries:</div>
                <div class="chat-tags-grid">${(m.queries || []).map(q => `<span class="chat-tag query">${esc(q)}</span>`).join("")}</div>
              </div>` : ""}
            ${m.role === "assistant" && (m.files_searched || []).length ? `
              <div class="chat-tags-section">
                <div class="chat-tags-label">${ICON.files} Files Searched:</div>
                <div class="chat-tags-grid">${(m.files_searched || []).map(f => `<span class="chat-tag file">${esc(formatFileTag(f))}</span>`).join("")}</div>
              </div>` : ""}
          `).join("")}
        </div>
        </div>
      </div>`;
    }).join("");

    results.querySelectorAll(".session-head").forEach(head => {
      const toggle = () => {
        const card = head.closest(".session-card");
        const open = card.classList.toggle("open");
        head.setAttribute("aria-expanded", String(open));
      };
      head.addEventListener("click", toggle);
      head.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); }
      });
    });
  } catch (err) {
    stats.hidden = true;
    results.innerHTML = stateBox("Could not load sessions", err.message, true);
  } finally {
    setLoading($("chats-submit"), false);
  }
});

/* ====================================================== Tickets Automation */
let taRows = [];

function taPayload() {
  return JSON.stringify({
    org_id: $("ta-org").value.trim(),
    date_from: $("ta-from").value || null,
    date_to: $("ta-to").value || null,
  });
}

$("ta-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const results = $("ta-results");
  const stats = $("ta-stats");
  setLoading($("ta-submit"), true);
  $("ta-download").disabled = true;
  $("ta-copy-panel").hidden = true;
  stats.hidden = true;
  results.innerHTML = skeleton(6);
  try {
    const data = await api("/api/ticket-automation/process", { method: "POST", body: taPayload() });
    taRows = data.rows;
    stats.innerHTML =
      statCard("Fetched from Jira", data.fetched) +
      statCard("Matched org", data.matched, "stat-info") +
      statCard("Sessions resolved", data.resolved, "stat-success") +
      statCard("Unresolved", data.unresolved, data.unresolved ? "stat-warning" : "");
    stats.hidden = false;

    if (!data.rows.length) {
      results.innerHTML = stateBox("No tickets matched",
        `No admin-note tickets found for Organization ID ${esc(data.org_id)} in the selected range.`);
      return;
    }
    $("ta-download").disabled = false;
    $("ta-copy-panel").hidden = false;
    results.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Ticket</th><th>Status</th><th>Created</th><th>Session URL</th><th>Note</th><th></th></tr></thead>
      <tbody>${data.rows.map((r, i) => `<tr>
        <td class="mono">${esc(r.ticket_id)}</td>
        <td><span class="badge">${esc(r.status || "—")}</span></td>
        <td class="mono">${esc(r.created || "—")}</td>
        <td>${r.session_url
          ? `<a href="${esc(r.session_url)}" target="_blank" rel="noopener">Open chat log</a>`
          : `<span class="badge badge-warning">Not found</span>`}</td>
        <td class="note-cell">${esc(r.note || "—")}</td>
        <td><button class="btn btn-secondary" style="min-height:36px;padding:0 12px" data-copy="${i}" title="Copy ticket | note">Copy</button></td>
      </tr>`).join("")}</tbody></table></div>`;

    results.querySelectorAll("[data-copy]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const r = taRows[Number(btn.dataset.copy)];
        await navigator.clipboard.writeText(`${r.ticket_id} | ${r.note}`);
        toast(`Copied ${r.ticket_id}`, "success");
      });
    });
  } catch (err) {
    stats.hidden = true;
    results.innerHTML = stateBox("Export failed", err.message, true);
  } finally {
    setLoading($("ta-submit"), false);
  }
});

$("ta-copy-all").addEventListener("click", async () => {
  if (!taRows.length) return;
  await navigator.clipboard.writeText(taRows.map(r => `${r.ticket_id} | ${r.note}`).join("\n"));
  toast(`Copied ${taRows.length} rows to clipboard`, "success");
});

$("ta-download").addEventListener("click", async () => {
  const btn = $("ta-download");
  setLoading(btn, true);
  try {
    const resp = await fetch("/api/ticket-automation/download", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: taPayload(),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { detail = (await resp.json()).detail || detail; } catch { /* not json */ }
      throw new Error(detail);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `org_${$("ta-org").value.trim()}_sessions.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Excel downloaded", "success");
  } catch (err) {
    toast(`Download failed: ${err.message}`, "error");
  } finally {
    setLoading(btn, false);
  }
});

/* ============================================================= OSD -> IMAP */
$("osd-dry").addEventListener("change", () => {
  $("osd-submit-label").textContent = $("osd-dry").checked ? "Preview copy" : "Copy tickets";
});

function osdList(items, cols) {
  return `<div class="table-wrap"><table>
    <thead><tr>${cols.map(c => `<th>${esc(c.label)}</th>`).join("")}</tr></thead>
    <tbody>${items.map(it => `<tr>${cols.map(c =>
      `<td class="${c.mono ? "mono" : c.wrap ? "note-cell" : ""}">${c.render ? c.render(it) : esc(it[c.key] ?? "—")}</td>`
    ).join("")}</tr>`).join("")}</tbody></table></div>`;
}

$("osd-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dry = $("osd-dry").checked;
  if (!dry && !window.confirm("This will create real tickets in the target project. Continue?")) return;
  const results = $("osd-results");
  const stats = $("osd-stats");
  setLoading($("osd-submit"), true);
  stats.hidden = true;
  results.innerHTML = skeleton(4);
  try {
    const data = await api("/api/osd-imap/copy", {
      method: "POST",
      body: JSON.stringify({ date: $("osd-date").value, dry_run: dry }),
    });
    const createdCount = dry ? data.would_create.length : data.created.length;
    stats.innerHTML =
      statCard(`Found in ${data.source_project}`, data.source_count) +
      statCard(dry ? "Would create" : "Created", createdCount, "stat-success") +
      statCard("Skipped (duplicate)", data.skipped.length, "stat-warning") +
      statCard("Errors", data.errors.length, data.errors.length ? "stat-danger" : "");
    stats.hidden = false;

    let html = "";
    if (dry && data.would_create.length) {
      html += `<div class="result-section"><h3><span class="badge badge-info">Dry run</span> Would be copied to ${esc(data.target_project)} (status: ${esc(data.target_status)})</h3>` +
        osdList(data.would_create, [
          { key: "key", label: "Source", mono: true },
          { key: "summary", label: "Summary", wrap: true },
        ]) + `</div>`;
    }
    if (!dry && data.created.length) {
      html += `<div class="result-section"><h3><span class="badge badge-success">Created</span> New tickets in ${esc(data.target_project)}</h3>` +
        osdList(data.created, [
          { key: "source_key", label: "Source", mono: true },
          { key: "new_key", label: "New ticket", mono: true },
          { key: "summary", label: "Summary", wrap: true },
        ]) + `</div>`;
    }
    if (data.skipped.length) {
      html += `<div class="result-section"><h3><span class="badge badge-warning">Skipped</span> Already exist in ${esc(data.target_project)}</h3>` +
        osdList(data.skipped, [
          { key: "key", label: "Source", mono: true },
          { key: "summary", label: "Summary", wrap: true },
        ]) + `</div>`;
    }
    if (data.errors.length) {
      html += `<div class="result-section"><h3><span class="badge badge-danger">Errors</span></h3>` +
        osdList(data.errors, [
          { key: "key", label: "Source", mono: true },
          { key: "summary", label: "Summary", wrap: true },
          { key: "error", label: "Error", wrap: true },
        ]) + `</div>`;
    }
    if (!html) html = stateBox("Nothing to copy", `No "Admin Note Created" tickets were created in ${esc(data.source_project)} on ${esc(data.date)}.`);
    results.innerHTML = html;
    toast(dry ? "Dry run complete — nothing was created" : `Copy complete: ${createdCount} created`, data.errors.length ? "error" : "success");
  } catch (err) {
    stats.hidden = true;
    results.innerHTML = stateBox("Copy failed", err.message, true);
  } finally {
    setLoading($("osd-submit"), false);
    $("osd-submit-label").textContent = $("osd-dry").checked ? "Preview copy" : "Copy tickets";
  }
});

/* ============================================================ Close Tickets */
let ctTickets = [];

function ctSelectedKeys() {
  return [...document.querySelectorAll("#ct-results .select-col input:checked")].map(cb => cb.value);
}

function ctUpdateToolbar() {
  const n = ctSelectedKeys().length;
  $("ct-selection-count").textContent = `${n} of ${ctTickets.length} selected`;
  $("ct-close-btn").disabled = n === 0;
}

$("ct-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pattern = $("ct-pattern").value.trim();
  const results = $("ct-results");
  setLoading($("ct-submit"), true);
  $("ct-toolbar").hidden = true;
  results.innerHTML = skeleton(6);
  try {
    const data = await api("/api/close-tickets/find", { method: "POST", body: JSON.stringify({ pattern }) });
    ctTickets = data.tickets;
    if (!ctTickets.length) {
      results.innerHTML = stateBox("No open tickets matched", `Nothing open matches "${pattern}".`);
      return;
    }
    $("ct-toolbar").hidden = false;
    results.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th class="select-col"><span class="sr-only">Select</span></th><th>Ticket</th><th>Summary</th><th>Result</th></tr></thead>
      <tbody>${ctTickets.map(t => `<tr data-key="${esc(t.key)}">
        <td class="select-col"><input type="checkbox" value="${esc(t.key)}" checked aria-label="Select ${esc(t.key)}"></td>
        <td class="mono">${esc(t.key)}</td>
        <td class="note-cell">${esc(t.summary)}</td>
        <td class="ct-result">—</td>
      </tr>`).join("")}</tbody></table></div>`;
    results.querySelectorAll(".select-col input").forEach(cb => cb.addEventListener("change", ctUpdateToolbar));
    ctUpdateToolbar();
  } catch (err) {
    results.innerHTML = stateBox("Search failed", err.message, true);
  } finally {
    setLoading($("ct-submit"), false);
  }
});

$("ct-select-all").addEventListener("click", () => {
  document.querySelectorAll("#ct-results .select-col input").forEach(cb => cb.checked = true);
  ctUpdateToolbar();
});
$("ct-select-none").addEventListener("click", () => {
  document.querySelectorAll("#ct-results .select-col input").forEach(cb => cb.checked = false);
  ctUpdateToolbar();
});

/* Confirm modal */
function confirmDialog(message) {
  return new Promise(resolve => {
    $("confirm-msg").textContent = message;
    $("confirm-backdrop").classList.add("open");
    const done = (val) => {
      $("confirm-backdrop").classList.remove("open");
      $("confirm-ok").onclick = $("confirm-cancel").onclick = null;
      document.onkeydown = null;
      resolve(val);
    };
    $("confirm-ok").onclick = () => done(true);
    $("confirm-cancel").onclick = () => done(false);
    document.onkeydown = (ev) => { if (ev.key === "Escape") done(false); };
    $("confirm-cancel").focus();
  });
}

const CT_STATUS_BADGE = {
  closed: `<span class="badge badge-success">Closed</span>`,
  already_closed: `<span class="badge badge-warning">Already closed</span>`,
  permission_denied: `<span class="badge badge-danger">Permission denied</span>`,
  error: `<span class="badge badge-danger">Error</span>`,
};

$("ct-close-btn").addEventListener("click", async () => {
  const keys = ctSelectedKeys();
  if (!keys.length) return;
  const ok = await confirmDialog(
    `You are about to close ${keys.length} ticket(s) in Jira. This transitions them to Done and is not easily undone.`);
  if (!ok) return;

  const btn = $("ct-close-btn");
  setLoading(btn, true);
  try {
    const workers = Number($("ct-workers").value) || 50;
    const data = await api("/api/close-tickets/close", {
      method: "POST",
      body: JSON.stringify({ keys, workers }),
    });
    data.results.forEach(r => {
      const row = document.querySelector(`#ct-results tr[data-key="${CSS.escape(r.key)}"]`);
      if (row) {
        row.querySelector(".ct-result").innerHTML =
          (CT_STATUS_BADGE[r.status] || esc(r.status)) + (r.detail ? ` <span class="mono" style="font-size:12px">${esc(r.detail)}</span>` : "");
        row.querySelector(".select-col input").checked = false;
      }
    });
    ctUpdateToolbar();
    const c = data.counts;
    toast(`Done: ${c.closed || 0} closed, ${c.already_closed || 0} already closed, ${(c.permission_denied || 0) + (c.error || 0)} failed`,
      (c.permission_denied || c.error) ? "error" : "success");
  } catch (err) {
    toast(`Bulk close failed: ${err.message}`, "error");
  } finally {
    setLoading(btn, false);
    ctUpdateToolbar();
  }
});
