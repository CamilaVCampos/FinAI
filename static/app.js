// FinAI front-end: plain functions, no framework. Texts live in i18n.js (t()).
let state = {
  analysis: null, filter: "all", month: null, currency: "USD", language: "en",
  status: null, billsData: { month: null, bills: [], recurring: [] }, history: [],
};

function $(sel) { return document.querySelector(sel); }

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function locale() { return LOCALES[state.language] || "en-US"; }

function money(value, currency = state.currency) {
  return new Intl.NumberFormat(locale(), { style: "currency", currency }).format(value || 0);
}

// "2026-11" -> "November 2026" / "noviembre de 2026"
function monthName(key, style = "long") {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString(locale(), { month: style, year: "numeric" });
}

// "2026-11-09" -> "Nov 9" / "9 nov"
function shortDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleString(locale(), { month: "short", day: "numeric" });
}

function capitalize(text) { return text.charAt(0).toUpperCase() + text.slice(1); }

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
  return data;
}

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 4500);
}

// Blocking loading screen: the user waits with a spinner instead of seeing half-updated screens.
function showLoading(key) {
  $("#loading-text").textContent = t(key);
  $("#loading").classList.remove("hidden");
}
function hideLoading() { $("#loading").classList.add("hidden"); }

// ---------- Confirmation dialog ----------
function confirmDialog({ title, body, extraHtml = "", okText }) {
  return new Promise((resolve) => {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = body;
    $("#modal-extra").innerHTML = extraHtml;
    $("#modal-ok").textContent = okText || t("modal.confirm");
    $("#modal").classList.remove("hidden");
    const close = (value) => {
      $("#modal").classList.add("hidden");
      $("#modal-ok").onclick = null;
      $("#modal-cancel").onclick = null;
      resolve(value);
    };
    $("#modal-ok").onclick = () => close(true);
    $("#modal-cancel").onclick = () => close(false);
  });
}

// When the user's currency differs from the PayPal account's, show what will really be sent.
function payoutNote(amount) {
  const fx = state.analysis && state.analysis.fx;
  const paypal = (state.status && state.status.paypal_currency) || "USD";
  if (!fx || paypal === state.currency || !fx.rate_to_paypal) return "";
  return `<p class="small muted">${esc(t("pay.converted", {
    paypal, amount: money(amount * fx.rate_to_paypal, paypal), date: fx.date || "",
  }))}</p>`;
}

// ---------- Tabs ----------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.id === `tab-${name}`));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  window.scrollTo(0, 0);
}

// ---------- Status ----------
async function loadStatus() {
  state.status = await api("/api/status");
  renderStatus();
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  const badge = (ok, okText, warnText) => `<span class="badge ${ok ? "ok" : "warn"}">${ok ? okText : warnText}</span>`;
  $("#badges").innerHTML =
    badge(s.paypal_configured, t("badge.paypal", { env: s.environment }), t("badge.paypal_off")) +
    badge(s.ai_configured, t("badge.ai"), t("badge.ai_off"));
}

// ---------- Analysis / Home ----------
async function loadAnalysis(refresh = false) {
  const a = await api("/api/analysis" + (refresh ? "?refresh=1" : ""));
  state.analysis = a;
  state.currency = a.currency || "USD";
  state.language = a.language || state.language;
  const keys = a.months.map((m) => m.key);
  if (!keys.includes(state.month) && state.month !== "all") state.month = a.months[a.months.length - 1].key;
  renderAll();
}

function renderAll() {
  applyStaticTranslations();
  renderStatus();
  const a = state.analysis;
  if (a) {
    renderBanner(a);
    renderHome(a);
    renderMonthFilters(a);
    renderTransactions(true);
    renderGoals(a.goals, a.suggested_monthly_saving);
  }
  renderBills();
  renderHistory();
  $("#income-label").textContent = t("profile.income", { currency: state.currency });
}

function joinNames(names) {
  return names.length <= 1 ? names.join("") : names.slice(0, -1).join(", ") + ` ${t("note.and")} ` + names[names.length - 1];
}

function sourceText(a) {
  const note = a.source_note || {};
  if (note.problem) return t(`note.${note.problem}`);
  const current = a.months[a.months.length - 1];
  if (current.source === "sample") return t("note.no_current");
  let text = "";
  if (note.today_month && note.focus_month !== note.today_month) {
    text = t("note.focus_past", { today: monthName(note.today_month), focus: monthName(note.focus_month) }) + " ";
  }
  text += t("note.live", { month: monthName(current.key) });
  if (note.sample_months && note.sample_months.length) {
    text += " " + t("note.sample_history", { months: joinNames(note.sample_months.map((k) => monthName(k))) });
  }
  return text;
}

function renderBanner(a) {
  const el = $("#source-banner");
  el.textContent = (a.source === "paypal" ? "" : t("note.sample_prefix")) + capitalize(sourceText(a));
  el.className = "banner" + (a.source === "paypal" ? " live" : "");

  const fx = a.fx || {};
  let fxText = fx.converted_count ? t("fx.note", { currency: a.currency, source: "Frankfurter (ECB)", date: fx.date || "" }) : "";
  if (fx.missing_count) fxText += " " + t("fx.missing", { count: fx.missing_count });
  $("#fx-note").textContent = fxText;
}

function sourceTag(source) {
  return source === "paypal"
    ? `<span class="src paypal">${t("tag.paypal")}</span>`
    : `<span class="src sample">${t("tag.sample")}</span>`;
}

function renderHero(a) {
  const b = a.budget;
  const focus = a.months[a.months.length - 1];
  const left = b.income - b.spent;
  const over = left < 0;
  $("#hero-label").textContent = t(over ? "home.left_over" : "home.left", { month: monthName(focus.key, "long") });
  $("#hero-value").textContent = money(Math.abs(left));
  const pct = b.income > 0 ? Math.min((b.spent / b.income) * 100, 100) : 0;
  $("#hero-bar-fill").style.width = `${pct}%`;
  $("#hero-bar-fill").className = over ? "over" : "";
  $("#hero-sub").textContent = t("home.of_income", { spent: money(b.spent), income: money(b.income) });
  $("#stat-spent").textContent = money(b.spent);
  $("#stat-free").textContent = money(a.bills_forecast.free_after_bills);
  $("#score").textContent = a.score;
}

// Donut: what share of the income went to needs, wants, luxury, and what was left as savings.
function renderDonut(a) {
  const b = a.budget, p = b.percents;
  const want = a.totals.want, luxury = a.totals.luxury, need = b.needs.actual, saved = b.savings.actual;
  const base = Math.max(b.income, b.spent, 1);
  const parts = [[need, "var(--need)"], [want, "var(--want)"], [luxury, "var(--luxury)"], [saved, "var(--save)"]];
  let start = 0;
  const stops = parts.map(([v, color]) => {
    const end = start + (v / base) * 360;
    const stop = `${color} ${start}deg ${end}deg`;
    start = end;
    return stop;
  });
  stops.push(`var(--soft) ${start}deg 360deg`);
  $("#donut").style.background = `conic-gradient(${stops.join(", ")})`;
  $("#donut-pct").textContent = b.income > 0 ? `${Math.round((b.spent / b.income) * 100)}%` : "--";
  $("#budget-title").textContent = t("home.budget", { needs: Math.round(p.needs), wants: Math.round(p.wants), savings: Math.round(p.savings) });

  const share = (v) => (b.income > 0 ? Math.round((v / b.income) * 100) : 0);
  const pctText = (v) => Math.round(v * 10) / 10;
  const status = (actual, target, isSaving) => {
    if (isSaving) return actual >= target ? ["ok", t("home.ok")] : ["under", t("home.under")];
    return actual > target ? ["over", t("home.over")] : ["ok", t("home.ok")];
  };
  const row = (name, color, actual, subText, st) => `<div class="leg-row">
      <span class="dot" style="background:${color}"></span><span class="name">${name}</span><span class="val">${money(actual)}</span>
      <div class="sub"><span>${share(actual)}% · ${esc(subText)}</span>${st ? `<span class="status ${st[0]}">${st[1]}</span>` : ""}</div>
    </div>`;
  $("#donut-legend").innerHTML =
    row(t("legend.needs"), "var(--need)", need, t("home.target", { amount: money(b.needs.target), pct: pctText(p.needs) }),
      status(need, b.needs.target, false)) +
    row(t("legend.wants"), "var(--want)", want, t("home.wants_target", { amount: money(b.wants.target), pct: pctText(p.wants) }),
      status(b.wants.actual, b.wants.target, false)) +
    row(t("legend.luxury"), "var(--luxury)", luxury, t("home.inside_wants"), null) +
    row(t("legend.savings"), "var(--save)", saved, t("home.target", { amount: money(b.savings.target), pct: pctText(p.savings) }),
      status(saved, b.savings.target, true));
}

function renderMonths(a) {
  const months = a.months || [];
  const income = a.budget.income;
  const max = Math.max(income, ...months.map((m) => m.spent), 1);
  $("#month-bars").innerHTML = months.map((m) => {
    const left = income - m.spent;
    const seg = (value, color) => value > 0
      ? `<div style="width:${(value / max) * 100}%;background:${color}" title="${money(value)}"></div>` : "";
    const right = left >= 0
      ? `<span class="small saved">${t("home.month_saved", { amount: money(left) })}</span>`
      : `<span class="over-text">${t("home.month_over", { amount: money(-left) })}</span>`;
    return `<div class="month-row">
      <div class="bar-label">
        <span><strong>${esc(capitalize(monthName(m.key)))}</strong>${m.current ? " " + t("home.so_far") : ""} ${sourceTag(m.source)}</span>
        <span class="month-right">${money(m.spent)} ${right}</span>
      </div>
      <div class="stack">${seg(m.totals.need, "var(--need)")}${seg(m.totals.want, "var(--want)")}${seg(m.totals.luxury, "var(--luxury)")}${seg(left, "var(--save)")}</div>
    </div>`;
  }).join("");
}

function renderHome(a) {
  renderHero(a);
  renderDonut(a);
  renderMonths(a);

  const sampleNote = a.profile_is_sample
    ? `<div class="note">${sourceTag("sample")} ${esc(t("home.sample_profile", { income: money(a.budget.income) }))} <a href="#" onclick="showTab('profile');return false;">${esc(t("home.enter_income"))}</a>.</div>`
    : "";
  $("#alerts").innerHTML = sampleNote + a.alerts.map((al) =>
    `<div class="alert"><i class="ti ti-alert-triangle"></i><span>${esc(t(`alert.${al.code}`, { amount: money(al.amount), pct: al.pct }))}</span></div>`).join("");

  $("#headline").textContent = a.headline;
  $("#ai-mode").textContent = t(a.ai_mode === "ai" ? "home.by_claude" : "home.basic");
  $("#insights").innerHTML = a.insights.map((x) => `<li>${esc(x)}</li>`).join("");
  $("#recommendation").textContent = a.recommendation;

  const goals = a.goals || [];
  const suggested = `<div><div class="small muted">${t("home.suggested")}</div>
      <strong>${t("home.per_month", { amount: money(a.suggested_monthly_saving) })}</strong></div>`;
  if (a.suggested_monthly_saving > 0 && goals.length) {
    $("#suggest-box").innerHTML = suggested + `<button class="btn" id="btn-save-now">${esc(t("home.save_toward", { goal: itemName(goals[0]) }))}</button>`;
    $("#btn-save-now").onclick = () => contribute(goals[0], a.suggested_monthly_saving);
  } else if (a.suggested_monthly_saving > 0) {
    $("#suggest-box").innerHTML = suggested + `<button class="btn ghost" onclick="showTab('goals')">${t("home.create_goal")}</button>`;
  } else {
    $("#suggest-box").innerHTML = "";
  }
}

// ---------- Transactions (AG Grid community edition) ----------
let txGrid = null;

function txType(tx) {
  if (tx.kind === "saving") return "saving";
  return tx.category || "income";
}

function passesFilters(tx) {
  if (state.month && state.month !== "all" && !tx.date.startsWith(state.month)) return false;
  if (state.filter === "all") return true;
  if (state.filter === "anomaly") return tx.is_anomaly;
  return tx.category === state.filter;
}

function txAmountText(tx) {
  const currency = tx.fx_missing ? tx.original_currency : state.currency;
  return (tx.direction === "in" ? "+" : "-") + money(tx.amount, currency);
}

function txColumns() {
  return [
    { field: "date", headerName: t("col.date"), width: 96, sort: "desc", valueFormatter: (p) => shortDate(p.value) },
    { field: "display_description", headerName: t("col.description"), flex: 1, minWidth: 150,
      cellRenderer: (p) => `${esc(p.value)}${p.data.is_anomaly ? ` <span class="flag" title="${esc(t("tag.unusual"))}">●</span>` : ""}` },
    { colId: "type", headerName: t("col.category"), width: 118, valueGetter: (p) => txType(p.data),
      getQuickFilterText: (p) => t(`cat.${p.value}`),
      cellRenderer: (p) => `<span class="cat ${p.value}">${esc(t(`cat.${p.value}`))}</span>` },
    { colId: "amount", headerName: t("col.amount"), width: 120, type: "rightAligned",
      valueGetter: (p) => (p.data.direction === "in" ? 1 : -1) * p.data.amount,
      valueFormatter: (p) => txAmountText(p.data),
      cellClass: (p) => "tx-amount " + p.data.direction },
  ];
}

function renderMonthFilters(a) {
  const options = [["all", t("filter.all_months")], ...a.months.map((m) => [m.key, capitalize(monthName(m.key, "short"))])];
  $("#month-filters").innerHTML = options.map(([key, label]) =>
    `<button class="chip month-chip ${state.month === key ? "active" : ""}" data-month="${key}">${esc(label)}</button>`).join("");
  document.querySelectorAll(".month-chip").forEach((chip) => {
    chip.onclick = () => {
      state.month = chip.dataset.month;
      document.querySelectorAll(".month-chip").forEach((c) => c.classList.toggle("active", c === chip));
      renderTransactions();
    };
  });
}

function updateTxCount() {
  if (!txGrid) return;
  let count = 0, spent = 0;
  txGrid.forEachNodeAfterFilter((node) => {
    if (!node.data) return;
    count += 1;
    if (node.data.direction === "out" && node.data.kind !== "saving") spent += node.data.amount;
  });
  $("#tx-count").textContent = t("spend.count", { count, amount: money(spent) });
}

function renderTransactions(rebuildColumns = false) {
  const a = state.analysis;
  if (!a) return;
  if (!window.agGrid) {
    $("#tx-grid").innerHTML = `<p class="muted">${t("spend.nolib")}</p>`;
    return;
  }
  if (!txGrid) {
    txGrid = agGrid.createGrid($("#tx-grid"), {
      columnDefs: txColumns(),
      rowData: [],
      defaultColDef: { sortable: true, resizable: true },
      getRowId: (p) => p.data.id,
      rowHeight: 46,
      overlayNoRowsTemplate: `<span class='muted'>${t("spend.empty")}</span>`,
      isExternalFilterPresent: () => true,
      doesExternalFilterPass: (node) => passesFilters(node.data),
      rowClassRules: { "row-unusual": (p) => p.data && p.data.is_anomaly },
      onRowClicked: (e) => openSheet(e.data),
      onModelUpdated: updateTxCount,
    });
  } else if (rebuildColumns) {
    txGrid.setGridOption("columnDefs", txColumns());
    txGrid.setGridOption("overlayNoRowsTemplate", `<span class='muted'>${t("spend.empty")}</span>`);
  }
  txGrid.setGridOption("rowData", a.transactions);
  txGrid.onFilterChanged();
}

// ---------- Transaction detail sheet ----------
function openSheet(tx) {
  const type = txType(tx);
  const rows = [];
  const row = (k, v) => rows.push(`<div class="detail-row"><div class="k">${esc(k)}</div><div>${v}</div></div>`);
  if (tx.display_description !== tx.description) row(t("detail.original_name"), esc(tx.description));
  row(t("col.date"), esc(new Date(tx.date + "T12:00:00").toLocaleDateString(locale(), { weekday: "long", year: "numeric", month: "long", day: "numeric" })));
  row(t("col.category"), `<span class="cat ${type}">${esc(t(`cat.${type}`))}</span>`);
  if (tx.converted || tx.fx_missing) {
    row(t("detail.charged"), `${esc(money(tx.original_amount, tx.original_currency))}${tx.fx_missing ? ` <span class="flag">${t("tag.not_converted")}</span>` : ""}`);
  }
  if (tx.label) row(t("detail.label"), esc(tx.label));
  if (tx.category) row(t("detail.unusual"), tx.is_anomaly ? `<span class="flag">${t("detail.yes")}</span>` : t("detail.no"));
  row(t("detail.source"), sourceTag(tx.source));
  if (tx.reason) rows.push(`<div class="detail-row"><div class="k">${esc(t("detail.reason"))}</div><div class="reason-box"><i class="ti ti-sparkles"></i> ${esc(tx.reason)}</div></div>`);
  row(t("detail.id"), `<span class="small muted">${esc(tx.id)}</span>`);

  $("#sheet-body").innerHTML = `
    <div class="sheet-amount ${tx.direction === "in" ? "tx-amount in" : ""}">${esc(txAmountText(tx))}</div>
    <div class="sheet-desc">${esc(tx.display_description)}</div>
    ${rows.join("")}`;
  $("#sheet-backdrop").classList.remove("hidden");
  $("#sheet").classList.add("open");
  $("#sheet").setAttribute("aria-hidden", "false");
}

function closeSheet() {
  $("#sheet").classList.remove("open");
  $("#sheet").setAttribute("aria-hidden", "true");
  $("#sheet-backdrop").classList.add("hidden");
}

// ---------- Goals ----------
function goalEta(g, monthlySaving) {
  if (g.status === "reached") return t("goals.reached");
  if (g.status === "no_saving" || !g.months) return t("goals.no_saving");
  return t("goals.eta", { amount: money(monthlySaving), months: g.months, eta: monthName(g.eta) });
}

function renderGoals(goals, monthlySaving) {
  $("#goal-list").innerHTML = goals.length ? goals.map((g) => {
    const pct = g.target > 0 ? Math.min((g.saved / g.target) * 100, 100) : 0;
    return `<div class="goal">
      <div class="bar-label"><strong>${esc(itemName(g))}${g.sample ? " " + sourceTag("sample") : ""}</strong><span>${money(g.saved)} / ${money(g.target)}</span></div>
      <div class="bar"><div style="width:${pct}%;background:var(--primary)"></div></div>
      <div class="tx-meta">${esc(goalEta(g, monthlySaving))}</div>
      <div class="goal-actions">
        <button class="btn" data-contribute="${g.id}"><i class="ti ti-arrow-up-right"></i> ${t("goals.transfer")}</button>
        <button class="btn danger" data-delete-goal="${g.id}">${t("goals.delete")}</button>
      </div>
    </div>`;
  }).join("") : `<p class="muted">${t("goals.empty")}</p>`;

  document.querySelectorAll("[data-contribute]").forEach((btn) => {
    btn.onclick = () => {
      const goal = goals.find((g) => g.id === btn.dataset.contribute);
      contribute(goal, monthlySaving || 0);
    };
  });
  document.querySelectorAll("[data-delete-goal]").forEach((btn) => {
    btn.onclick = async () => {
      const ok = await confirmDialog({ title: t("goals.delete_title"), body: esc(t("goals.delete_body")), okText: t("goals.delete") });
      if (!ok) return;
      await api(`/api/goals/${btn.dataset.deleteGoal}`, { method: "DELETE" });
      await loadAnalysis();
    };
  });
}

async function contribute(goal, suggested) {
  const pending = confirmDialog({
    title: t("goals.transfer_title", { goal: itemName(goal) }),
    body: t("goals.transfer_body"),
    extraHtml: `<label class="small muted">${esc(t("goals.amount", { currency: state.currency }))}</label>
      <input id="contrib-amount" type="number" min="0.01" step="0.01" value="${(suggested || 0).toFixed(2)}">
      <div id="contrib-fx">${payoutNote(suggested || 0)}</div>`,
    okText: t("goals.confirm"),
  });
  $("#contrib-amount").oninput = (e) => { $("#contrib-fx").innerHTML = payoutNote(parseFloat(e.target.value) || 0); };
  const ok = await pending;
  if (!ok) return;
  const amount = parseFloat($("#contrib-amount").value);
  try {
    const res = await api(`/api/goals/${goal.id}/contribute`, { method: "POST", body: { amount, confirm: true } });
    toast(t("goals.sent", { amount: money(amount), batch: res.payout.payout_batch_id, status: res.payout.status }));
    await Promise.all([loadAnalysis(), loadHistory()]);
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadHistory() {
  state.history = await api("/api/history");
  renderHistory();
}

function renderHistory() {
  const items = state.history || [];
  $("#history-list").innerHTML = items.length ? items.map((h) => {
    const sent = h.sent_currency && h.sent_currency !== (h.currency || h.sent_currency)
      ? ` · ${t("history.sent", { amount: money(h.sent_amount, h.sent_currency) })}` : "";
    const name = h.type === "saving" ? h.goal : h.bill;
    return `<div class="tx">
      <div>
        <div class="tx-desc">${esc(t(h.type === "saving" ? "history.saved" : "history.paid", { name: itemName({ name, sample: true }) }))}</div>
        <div class="tx-meta">${esc(h.date.replace("T", " "))} · ${esc(t("history.batch", { batch: h.payout_batch_id }))} · ${esc(h.status)}${esc(sent)}</div>
      </div>
      <div class="tx-amount">${money(h.amount, h.currency || "USD")}</div>
    </div>`;
  }).join("") : t("history.empty");
}

// ---------- Bills, recurring payments and calendar ----------
async function loadBills() {
  state.billsData = await api("/api/bills");
  renderBills();
}

// Recurring payments come from transaction descriptions: show them in the user's language.
function recurringName(r) {
  const tx = state.analysis && state.analysis.transactions.find((x) => x.description === r.name);
  return tx ? tx.display_description : r.name;
}

function renderBills() {
  const data = state.billsData;
  if (!data.month) return;
  renderCalendar(data);
  renderBillList(data.bills);
  renderRecurring(data.recurring);
}

function renderCalendar(data) {
  const [year, monthNum] = data.month.split("-").map(Number);
  const month = monthNum - 1;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstWeekday = new Date(year, month, 1).getDay();
  const now = new Date();
  const isThisMonth = now.getFullYear() === year && now.getMonth() === month;
  $("#cal-title").textContent = capitalize(monthName(data.month));

  // Each item sits on the day it was paid, or on its due day while it is still pending.
  const items = [
    ...data.bills.map((b) => ({ name: itemName(b), amount: b.amount, day: b.day, paidOn: b.paid_on, auto: false })),
    ...data.recurring.map((r) => ({ name: recurringName(r), amount: r.amount, day: r.day, paidOn: r.paid_on, auto: true })),
  ].map((x) => ({ ...x, showDay: x.paidOn ? Number(x.paidOn.slice(8, 10)) : Math.min(x.day, daysInMonth) }));

  // Weekday names in the user's language, starting on Sunday (Jan 4 2026 was a Sunday).
  const weekdays = [...Array(7)].map((_, i) => new Date(2026, 0, 4 + i).toLocaleString(locale(), { weekday: "short" }));
  let html = weekdays.map((d) => `<div class="cal-head">${esc(d)}</div>`).join("");
  for (let i = 0; i < firstWeekday; i++) html += `<div class="cal-day empty"></div>`;
  for (let day = 1; day <= daysInMonth; day++) {
    const due = items.filter((x) => x.showDay === day);
    html += `<div class="cal-day ${isThisMonth && day === now.getDate() ? "today" : ""}">
      <div class="cal-num">${day}</div>
      ${due.map((x) => {
        const cls = x.paidOn ? "paid" : x.auto ? "auto" : "";
        const title = `${x.name} ${money(x.amount)}${x.paidOn ? " · " + t("bills.paid_on", { date: shortDate(x.paidOn) }) : ""}`;
        return `<div class="cal-item ${cls}" title="${esc(title)}">${x.paidOn ? "✓ " : ""}${esc(x.name)}</div>`;
      }).join("")}
    </div>`;
  }
  $("#calendar").innerHTML = html;

  const pending = items.filter((x) => !x.paidOn);
  const total = pending.reduce((s, x) => s + Number(x.amount), 0);
  $("#bills-summary").textContent = items.length ? t("bills.pending", { count: pending.length, amount: money(total) }) : "";
}

function renderBillList(bills) {
  const sorted = [...bills].sort((a, b) => a.day - b.day);
  $("#bill-list").innerHTML = sorted.length ? sorted.map((b) => {
    const paidBadge = b.paid_on
      ? `<span class="badge ok" title="${b.paid_in_paypal ? esc(t("bills.paid_paypal_help")) : ""}">${esc(t("bills.paid_on", { date: shortDate(b.paid_on) }))}</span>` : "";
    return `<div class="bill">
      <div class="bill-main"><div class="bill-icon"><i class="ti ti-file-invoice"></i></div>
        <div><strong>${esc(itemName(b))}</strong>${b.sample ? " " + sourceTag("sample") : ""}<div class="tx-meta">${esc(t("bills.day_line", { day: b.day, amount: money(b.amount) }))}</div></div></div>
      <div class="goal-actions" style="margin:0">
        ${paidBadge || `<button class="btn" data-pay="${b.id}">${t("bills.pay")}</button>`}
        <button class="btn danger" data-delete-bill="${b.id}">${t("goals.delete")}</button>
      </div>
    </div>`;
  }).join("") : `<p class="muted">${t("bills.empty")}</p>`;

  document.querySelectorAll("[data-pay]").forEach((btn) => {
    btn.onclick = async () => {
      const bill = bills.find((b) => b.id === btn.dataset.pay);
      const ok = await confirmDialog({
        title: t("bills.pay_title", { name: itemName(bill) }),
        body: t("bills.pay_body", { amount: money(bill.amount) }),
        extraHtml: payoutNote(Number(bill.amount)),
        okText: t("bills.confirm"),
      });
      if (!ok) return;
      try {
        const res = await api(`/api/bills/${bill.id}/pay`, { method: "POST", body: { confirm: true } });
        toast(t("bills.paid", { amount: money(bill.amount), batch: res.payout.payout_batch_id }));
        await Promise.all([loadBills(), loadHistory(), loadAnalysis()]);
      } catch (err) {
        toast(err.message, true);
      }
    };
  });
  document.querySelectorAll("[data-delete-bill]").forEach((btn) => {
    btn.onclick = async () => {
      const ok = await confirmDialog({ title: t("bills.delete_title"), body: esc(t("bills.delete_body")), okText: t("goals.delete") });
      if (!ok) return;
      await api(`/api/bills/${btn.dataset.deleteBill}`, { method: "DELETE" });
      await Promise.all([loadBills(), loadAnalysis()]);
    };
  });
}

function renderRecurring(recurring) {
  $("#recurring-list").innerHTML = recurring.length ? recurring.map((r) => `
    <div class="bill">
      <div class="bill-main"><div class="bill-icon auto"><i class="ti ti-repeat"></i></div>
        <div><strong>${esc(recurringName(r))}</strong>
          <div class="tx-meta">${esc(t("bills.recurring_line", { day: r.day, amount: money(r.amount), months: r.months_seen }))}</div></div></div>
      <div class="goal-actions" style="margin:0">
        ${r.paid_on ? `<span class="badge ok">${esc(t("bills.paid_on", { date: shortDate(r.paid_on) }))}</span>` : ""}
        <button class="btn ghost" data-make-fixed="${r.id}"><i class="ti ti-plus"></i> ${t("bills.make_fixed")}</button>
      </div>
    </div>`).join("") : `<p class="muted small">${t("bills.recurring_empty")}</p>`;

  document.querySelectorAll("[data-make-fixed]").forEach((btn) => {
    btn.onclick = async () => {
      const r = recurring.find((x) => x.id === btn.dataset.makeFixed);
      try {
        await api("/api/bills", { method: "POST", body: { name: recurringName(r), amount: r.amount, day: r.day } });
        toast(t("bills.added"));
        await Promise.all([loadBills(), loadAnalysis()]);
      } catch (err) { toast(err.message, true); }
    };
  });
}

// ---------- Profile & settings ----------
async function loadProfile() {
  const p = await api("/api/profile");
  state.currency = p.currency || state.currency;
  state.language = p.language || state.language;
  const form = $("#profile-form");
  form.monthly_income.value = p.monthly_income || "";
  const pct = p.needs_percent != null && p.wants_percent != null
    ? { needs: p.needs_percent, wants: p.wants_percent, savings: p.savings_percent ?? 0 }
    : { needs: 50, wants: 50 - (p.savings_percent ?? 20), savings: p.savings_percent ?? 20 };
  form.needs_percent.value = pct.needs;
  form.wants_percent.value = pct.wants;
  form.savings_percent.value = pct.savings;
  updatePctTotal();
  const settings = $("#settings-form");
  settings.language.value = state.language;
  settings.currency.value = state.currency;
  applyStaticTranslations();
  $("#income-label").textContent = t("profile.income", { currency: state.currency });
}

function pctTotal() {
  const f = $("#profile-form");
  return ["needs_percent", "wants_percent", "savings_percent"].reduce((sum, n) => sum + (parseFloat(f[n].value) || 0), 0);
}

function updatePctTotal() {
  const total = Math.round(pctTotal() * 10) / 10;
  const ok = Math.abs(total - 100) < 0.01;
  const el = $("#pct-total");
  el.textContent = ok ? t("profile.total_ok") : t("profile.total_bad", { total });
  el.className = "pct-total" + (ok ? "" : " bad");
  return ok;
}

// ---------- Forms ----------
function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function wireForms() {
  $("#settings-form").onsubmit = async (e) => {
    e.preventDefault();
    const wanted = formData(e.target);
    state.language = wanted.language;  // the loading message already uses the new language
    showLoading("loading.settings");
    try {
      const res = await api("/api/settings", { method: "POST", body: wanted });
      const changed = res.from !== res.currency;
      state.currency = res.currency;
      await Promise.all([loadProfile(), loadBills(), loadAnalysis()]);
      toast(changed
        ? `${t("settings.saved")} · ${t("settings.converted", { from: res.from, rate: res.rate.toFixed(4), to: res.currency })}`
        : t("settings.saved"));
    } catch (err) {
      toast(err.message, true);
      await loadProfile().catch(() => {});
      renderAll();
    } finally {
      hideLoading();
    }
  };
  ["needs_percent", "wants_percent", "savings_percent"].forEach((n) => { $("#profile-form")[n].oninput = updatePctTotal; });
  $("#profile-form").onsubmit = async (e) => {
    e.preventDefault();
    if (!updatePctTotal()) { toast(t("profile.total_bad", { total: Math.round(pctTotal() * 10) / 10 }), true); return; }
    showLoading("loading.refresh");
    try {
      await api("/api/profile", { method: "POST", body: formData(e.target) });
      await loadAnalysis();
      toast(t("profile.saved"));
      showTab("home");
    } catch (err) { toast(err.message, true); } finally { hideLoading(); }
  };
  $("#goal-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/goals", { method: "POST", body: formData(e.target) });
      e.target.reset();
      toast(t("goals.added"));
      await loadAnalysis();
    } catch (err) { toast(err.message, true); }
  };
  $("#bill-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/bills", { method: "POST", body: formData(e.target) });
      e.target.reset();
      toast(t("bills.added"));
      await Promise.all([loadBills(), loadAnalysis()]);
    } catch (err) { toast(err.message, true); }
  };
}

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tabbar button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  document.querySelectorAll(".cat-chip").forEach((chip) => {
    chip.onclick = () => {
      document.querySelectorAll(".cat-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filter = chip.dataset.filter;
      renderTransactions();
    };
  });
  $("#tx-search").oninput = (e) => { if (txGrid) txGrid.setGridOption("quickFilterText", e.target.value); };
  $("#sheet-close").onclick = closeSheet;
  $("#sheet-backdrop").onclick = closeSheet;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
  $("#btn-refresh").onclick = async () => {
    showLoading("loading.refresh");
    try { await loadAnalysis(true); toast(t("spend.updated")); }
    catch (err) { toast(err.message, true); }
    finally { hideLoading(); }
  };
  wireForms();
  applyStaticTranslations();
  showLoading("loading.default");
  try {
    await loadProfile();
    showLoading("loading.default");
    await Promise.all([loadStatus(), loadHistory()]);
    await loadAnalysis();
    await loadBills();
  } catch (err) {
    toast(err.message, true);
  } finally {
    hideLoading();
  }
});
