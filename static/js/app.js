/* Library Management System - frontend logic (Fetch API, no page reloads) */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ---------- helpers ---------- */
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(url, options = {}) {
  const init = { method: "GET", ...options };
  if (init.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(init.body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error("Cannot reach the server. Is Flask running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.toggle("error", isError);
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

function spineColour(category) {
  let h = 0;
  for (const ch of category) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 42% 38%)`;
}

const today = () => new Date().toISOString().slice(0, 10);

/* ---------- state ---------- */
let members = [];
let issueBookId = null;
let deleteBookId = null;

/* ---------- stats ---------- */
async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").innerHTML = `
    <div class="stat"><b>${s.total}</b><span>Books in catalogue</span></div>
    <div class="stat"><b>${s.available}</b><span>Available now</span></div>
    <div class="stat"><b>${s.issued}</b><span>Currently issued</span></div>
    <div class="stat ${s.overdue ? "warn" : ""}"><b>${s.overdue}</b><span>Overdue</span></div>
    <div class="stat"><b>${s.members}</b><span>Members</span></div>`;

  const select = $("#filter-category");
  const current = select.value;
  select.innerHTML = '<option value="">All categories</option>' +
    s.categories.map((c) => `<option>${esc(c)}</option>`).join("");
  select.value = s.categories.includes(current) ? current : "";
  $("#category-options").innerHTML = s.categories.map((c) => `<option value="${esc(c)}">`).join("");
}

/* ---------- books ---------- */
async function loadBooks() {
  const params = new URLSearchParams();
  const q = $("#search").value.trim();
  if (q) params.set("q", q);
  if ($("#filter-status").value) params.set("status", $("#filter-status").value);
  if ($("#filter-category").value) params.set("category", $("#filter-category").value);

  const books = await api("/api/books?" + params);
  const list = $("#book-list");
  if (!books.length) {
    list.innerHTML = `<li class="empty">${
      q || params.size ? "No books match your search. Try a different title, author or ISBN." : "No books yet. Use “Add book” to start the catalogue."
    }</li>`;
    return;
  }
  list.innerHTML = books.map(bookRow).join("");
}

function bookRow(b) {
  const issued = b.status === "Issued";
  const late = issued && b.due_date < today();
  return `
  <li class="book" style="--spine:${spineColour(b.category)}">
    <span class="spine"></span>
    <div class="info">
      <h3>${esc(b.title)}</h3>
      <div class="meta">${esc(b.author)} &nbsp;|&nbsp; ISBN ${esc(b.isbn)} &nbsp;|&nbsp; ${esc(b.category)}</div>
    </div>
    <div class="side">
      ${issued ? `<span class="due ${late ? "late" : ""}">${esc(b.issued_to)}, due ${esc(b.due_date)}</span>` : ""}
      <span class="badge ${issued ? "issued" : "available"}">${esc(b.status)}</span>
      ${issued
        ? `<button class="btn small" data-act="return" data-id="${b.id}">Return</button>`
        : `<button class="btn small primary" data-act="issue" data-id="${b.id}" data-title="${esc(b.title)}">Issue</button>`}
      <button class="btn small ghost" data-act="delete" data-id="${b.id}" data-title="${esc(b.title)}">Delete</button>
    </div>
  </li>`;
}

/* ---------- members & history ---------- */
async function loadMembers() {
  members = await api("/api/members");
  $("#member-rows").innerHTML = members.length
    ? members.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.email)}</td><td>${esc(m.phone || "-")}</td>
        <td>${esc(m.joined_on)}</td><td>${m.books_held} of 3</td></tr>`).join("")
    : '<tr><td colspan="5" class="muted">No members yet. Add one before issuing books.</td></tr>';
}

async function loadHistory() {
  const items = await api("/api/issues");
  $("#history-rows").innerHTML = items.length
    ? items.map((i) => `<tr><td>${esc(i.title)}</td><td>${esc(i.member)}</td><td>${esc(i.issue_date)}</td>
        <td>${esc(i.due_date)}</td><td>${esc(i.return_date || "Not returned")}</td>
        <td>${i.fine ? "Rs " + i.fine : "-"}</td></tr>`).join("")
    : '<tr><td colspan="6" class="muted">Nothing has been issued yet.</td></tr>';
}

async function refreshAll() {
  await Promise.all([loadStats(), loadBooks(), loadMembers(), loadHistory()]);
}

/* ---------- tabs ---------- */
$$(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => {
      const on = t === tab;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on);
      $("#tab-" + t.dataset.tab).hidden = !on;
    });
  })
);

/* ---------- search / filters (debounced) ---------- */
let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadBooks().catch((e) => toast(e.message, true)), 250);
});
["#filter-status", "#filter-category"].forEach((sel) =>
  $(sel).addEventListener("change", () => loadBooks().catch((e) => toast(e.message, true)))
);

/* ---------- dialogs ---------- */
function openDialog(dlg) {
  const err = $(".form-error", dlg);
  if (err) err.textContent = "";
  dlg.showModal();
}
$$("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));

// submit handler that keeps the dialog open when the server reports an error
function onSubmit(formSel, handler) {
  const form = $(formSel);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dlg = form.closest("dialog");
    try {
      await handler(Object.fromEntries(new FormData(form)));
      dlg.close();
      form.reset();
    } catch (err) {
      const box = $(".form-error", dlg);
      if (box) box.textContent = err.message;
      else toast(err.message, true);
    }
  });
}

$("#btn-add-book").addEventListener("click", () => openDialog($("#dlg-book")));
$("#btn-add-member").addEventListener("click", () => openDialog($("#dlg-member")));

onSubmit("#form-book", async (data) => {
  const book = await api("/api/books", { method: "POST", body: data });
  toast(`Added “${book.title}”.`);
  await Promise.all([loadBooks(), loadStats()]);
});

onSubmit("#form-member", async (data) => {
  const m = await api("/api/members", { method: "POST", body: data });
  toast(`Added member ${m.name}.`);
  await Promise.all([loadMembers(), loadStats()]);
});

onSubmit("#form-issue", async (data) => {
  const book = await api(`/api/books/${issueBookId}/issue`, { method: "POST", body: { member_id: data.member_id } });
  toast(`Issued “${book.title}” to ${book.issued_to}. Due ${book.due_date}.`);
  await refreshAll();
});

onSubmit("#form-delete", async () => {
  const res = await api(`/api/books/${deleteBookId}`, { method: "DELETE" });
  toast(res.message);
  await refreshAll();
});

/* ---------- row buttons (event delegation) ---------- */
$("#book-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.dataset.id;
  try {
    if (btn.dataset.act === "issue") {
      if (!members.length) return toast("Add a member first, then issue the book.", true);
      issueBookId = id;
      $("#issue-title").textContent = btn.dataset.title;
      $("#issue-member").innerHTML = members
        .map((m) => `<option value="${m.id}">${esc(m.name)} (${m.books_held} of 3 held)</option>`).join("");
      openDialog($("#dlg-issue"));
    } else if (btn.dataset.act === "return") {
      const b = await api(`/api/books/${id}/return`, { method: "POST" });
      toast(b.fine ? `Returned “${b.title}”. Late fine: Rs ${b.fine}.` : `Returned “${b.title}”.`);
      await refreshAll();
    } else if (btn.dataset.act === "delete") {
      deleteBookId = id;
      $("#delete-title").textContent = btn.dataset.title;
      openDialog($("#dlg-delete"));
    }
  } catch (err) {
    toast(err.message, true);
    refreshAll().catch(() => {});
  }
});

refreshAll().catch((e) => toast(e.message, true));
