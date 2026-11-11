// FinAI front-end: plain functions, no framework. Texts live in i18n.js (t()).
let state = {
  analysis: null, filter: "all", month: null, currency: "USD", language: "en",
  status: null, billsData: { month: null, bills: [], recurring: [] }, history: [],
  calMonth: null, calData: null,
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
  if (!resp.ok) {
    // Known problems come with a code, so the message can be shown in the user's language.
    const known = data.code && t(`err.${data.code}`) !== `err.${data.code}` ? t(`err.${data.code}`, data) : null;
    throw new Error(known || data.error || `Request failed (${resp.status})`);
  }
  return data;
}

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), isError ? 8000 : 4500);
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
  if (name === "spending" && !guideState().spending) { saveGuide({ spending: true }); renderGuide(); }
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
let analysisRequest = 0;

async function loadAnalysis(refresh = false) {
  // Only the newest request may update the screen: an older, slower answer (e.g. from before
  // a goal was added) must never overwrite a newer one.
  const mine = ++analysisRequest;
  // "quick": the numbers come back at once. If Claude hasn't analyzed this data yet, the server
  // answers with the keyword rules (ai_pending) and Claude's analysis is fetched in the background.
  const a = await api("/api/analysis" + (refresh ? "?refresh=1" : "?quick=1"));
  if (mine !== analysisRequest) return state.analysis;
  applyAnalysis(a);
  if (a.ai_pending) waitForClaude(mine);
  return a;
}

async function waitForClaude(mine) {
  try {
    const full = await api("/api/analysis");
    if (mine === analysisRequest) applyAnalysis(full);
  } catch (err) {
    if (mine === analysisRequest) toast(err.message, true);
  }
}

function applyAnalysis(a) {
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
  const demo = document.createElement("span");
  demo.className = "banner-demo";
  demo.textContent = t("demo.note");
  el.appendChild(demo);
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
  const left = b.balance;  // income - spent - money moved to savings goals
  const over = left < 0;
  $("#hero-label").textContent = t(over ? "home.left_over" : "home.left", { month: monthName(focus.key, "long") });
  $("#hero-value").textContent = money(Math.abs(left));
  const pct = b.income > 0 ? Math.min(((b.spent + b.transfers) / b.income) * 100, 100) : 0;
  $("#hero-bar-fill").style.width = `${pct}%`;
  $("#hero-bar-fill").className = over ? "over" : "";
  $("#hero-sub").textContent = b.transfers > 0
    ? t("home.of_income_saved", { spent: money(b.spent), saved: money(b.transfers), income: money(b.income) })
    : t("home.of_income", { spent: money(b.spent), income: money(b.income) });
  $("#stat-spent").textContent = money(b.spent);
  $("#stat-free").textContent = money(a.bills_forecast.free_after_bills);
  $("#score").textContent = a.score;
  renderHealth(a);
}

// Tap the Health score to see how it was calculated, part by part.
function renderHealth(a) {
  const h = a.health;
  if (!h) return;
  const b = a.budget;
  const why = {
    savings: t("health.why_savings", { target: money(b.savings.target) }),
    needs: t(b.needs.actual > b.needs.target ? "health.why_over" : "health.why_within",
      { amount: money(Math.abs(b.needs.actual - b.needs.target)) }),
    wants: t(b.wants.actual > b.wants.target ? "health.why_over" : "health.why_within",
      { amount: money(Math.abs(b.wants.actual - b.wants.target)) }),
    unusual: t("health.why_unusual", { count: h.anomalies }),
  };
  $("#health-detail").innerHTML = `<div class="health-title">${esc(t("health.title"))}</div>` +
    h.parts.map((p) => `<div class="health-row">
      <span>${esc(t(`health.${p.code}`))}<small>${esc(why[p.code])}</small></span>
      <strong>${p.points.toLocaleString(locale())} / ${p.max}</strong></div>`).join("") +
    `<div class="health-row total"><span>${esc(t("health.total"))}</span><strong>${h.score} / 100</strong></div>`;
}

// Donut: what share of the income went to needs, wants, luxury, and what was left as savings.
function renderDonut(a) {
  const b = a.budget, p = b.percents;
  const want = a.totals.want, luxury = a.totals.luxury, need = b.needs.actual, saved = b.savings.actual;
  const unspent = b.unspent || 0;
  const base = Math.max(b.income, b.spent + b.transfers, 1);
  const parts = [[need, "var(--need)"], [want, "var(--want)"], [luxury, "var(--luxury)"], [saved, "var(--save)"], [unspent, "var(--unspent)"]];
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
    // Same rule as the health score: money not spent yet must first cover this month's remaining bills.
    const reachable = actual + (b.unspent_after_bills ?? unspent);
    if (isSaving) return reachable >= target ? ["ok", t("home.ok")] : ["under", t("home.under")];
    return actual > target ? ["over", t("home.over")] : ["ok", t("home.ok")];
  };
  const row = (name, color, actual, subText, st) => `<div class="leg-row">
      <span class="dot" style="background:${color}"></span><span class="name">${name}</span><span class="val">${money(actual)}</span>
      <div class="sub"><span>${share(actual)}% · ${esc(subText)}</span>${st ? `<span class="status ${st[0]}">${st[1]}</span>` : ""}</div>
    </div>`;
  $("#donut-legend").innerHTML =
    row(t("legend.needs"), "var(--need)", need, t("home.target", { amount: money(b.needs.target), pct: pctText(p.needs) }),
      status(need, b.needs.target, false)) +
    // The status compares wants + luxury with the target, so the row shows that total too.
    row(t("legend.wants"), "var(--want)", want, t("home.wants_target", { total: share(b.wants.actual), amount: money(b.wants.target), pct: pctText(p.wants) }),
      status(b.wants.actual, b.wants.target, false)) +
    row(t("legend.luxury"), "var(--luxury)", luxury, t("home.inside_wants"), null) +
    row(t("legend.savings"), "var(--save)", saved, t("home.target", { amount: money(b.savings.target), pct: pctText(p.savings) }),
      status(saved, b.savings.target, true)) +
    (b.running ? row(t("legend.unspent"), "var(--unspent)", unspent, t("home.unspent_sub"), null) : "");
}

function renderMonths(a) {
  const months = a.months || [];
  const income = a.budget.income;
  const max = Math.max(income, ...months.map((m) => m.spent + (m.saved || 0)), 1);
  $("#month-bars").innerHTML = months.map((m) => {
    // Moved to goals is saved. What is left of a month that is still running is only
    // "not spent yet" (gray); once the month is over, what was left counts as saved.
    const moved = m.saved || 0;
    const left = income - m.spent - moved;
    const saved = m.current ? moved : moved + Math.max(left, 0);
    const unspent = m.current ? Math.max(left, 0) : 0;
    const seg = (value, color) => value > 0
      ? `<div style="width:${(value / max) * 100}%;background:${color}" title="${money(value)}"></div>` : "";
    let right = left < 0 ? `<span class="over-text">${t("home.month_over", { amount: money(-left) })}</span>` : "";
    if (saved > 0) right += `<span class="small saved">${t("home.month_saved", { amount: money(saved) })}</span>`;
    if (unspent > 0) right += `<span class="small unspent-text">${t("home.month_unspent", { amount: money(unspent) })}</span>`;
    return `<div class="month-row">
      <div class="bar-label">
        <span><strong>${esc(capitalize(monthName(m.key)))}</strong>${m.current ? " " + t("home.so_far") : ""} ${sourceTag(m.source)}</span>
        <span class="month-right">${money(m.spent)} ${right}</span>
      </div>
      <div class="stack">${seg(m.totals.need, "var(--need)")}${seg(m.totals.want, "var(--want)")}${seg(m.totals.luxury, "var(--luxury)")}${seg(saved, "var(--save)")}${seg(unspent, "var(--unspent)")}</div>
    </div>`;
  }).join("");
}

function renderHome(a) {
  renderHero(a);
  renderDonut(a);
  renderMonths(a);

  // The sample-profile note sits above the blue card, so it is read before the numbers.
  $("#sample-note").innerHTML = a.profile_is_sample
    ? `<div class="note">${sourceTag("sample")} ${esc(t("home.sample_profile", { income: money(a.budget.income) }))} <a href="#" onclick="showTab('profile');return false;">${esc(t("home.enter_income"))}</a>.</div>`
    : "";
  const preliminary = a.ai_pending ? `<div class="note info"><i class="ti ti-loader-2 spin"></i> ${esc(t("home.preliminary"))}</div>` : "";
  $("#alerts").innerHTML = preliminary + a.alerts.map((al) =>
    `<div class="alert"><i class="ti ti-alert-triangle"></i><span>${esc(t(`alert.${al.code}`, { amount: money(al.amount), pct: al.pct }))}</span></div>`).join("");
  renderGuide();

  // While Claude works, the AI card says so instead of showing the keyword-rule text.
  $("#ai-card").classList.toggle("waiting", !!a.ai_pending);
  $("#ai-mode").textContent = t(a.ai_pending ? "home.claude_working_pill" : a.ai_mode === "ai" ? "home.by_claude" : "home.basic");
  $("#headline").innerHTML = a.ai_pending
    ? `<i class="ti ti-loader-2 spin"></i> ${esc(t("home.claude_working"))}` : esc(a.headline);
  $("#comparison").textContent = a.ai_pending ? "" : a.comparison || "";
  $("#comparison").hidden = a.ai_pending || !a.comparison;
  $("#insights").innerHTML = a.ai_pending ? "" : a.insights.map((x) => `<li>${esc(x)}</li>`).join("");
  $("#recommendation").textContent = a.ai_pending ? "" : a.recommendation;
  renderPlanImpact(a);

  const goals = a.goals || [];
  const suggested = `<div><div class="small muted">${t("home.suggested")}</div>
      <strong>${t("home.per_month", { amount: money(a.suggested_monthly_saving) })}</strong></div>`;
  if (a.ai_pending) {
    $("#suggest-box").innerHTML = "";
  } else if (a.suggested_monthly_saving > 0 && goals.some((g) => g.status !== "reached" && goalMonthly(g) > 0)) {
    // The first goal that still needs money, with the same monthly amount the Goals tab shows.
    const goal = goals.find((g) => g.status !== "reached" && goalMonthly(g) > 0);
    $("#suggest-box").innerHTML = suggested + `<button class="btn" id="btn-save-now">${esc(t("home.save_toward", { goal: itemName(goal) }))}</button>`;
    $("#btn-save-now").onclick = () => contribute(goal, goalMonthly(goal));
  } else if (a.suggested_monthly_saving > 0) {
    $("#suggest-box").innerHTML = suggested + `<button class="btn ghost" onclick="showTab('goals')">${t("home.create_goal")}</button>`;
  } else {
    $("#suggest-box").innerHTML = "";
  }
}

// Before / after: the first goal at today's saving pace vs with Claude's plan (numbers from the app).
function renderPlanImpact(a) {
  const p = a.plan_impact;
  const box = $("#plan-impact");
  if (a.ai_pending || !p) { box.innerHTML = ""; box.hidden = true; return; }
  const when = (x) => (x.eta ? capitalize(monthName(x.eta, "long")) : t("impact.never"));
  const goal = itemName({ name: p.goal, sample: p.goal_sample });
  box.hidden = false;
  box.innerHTML = `<div class="impact-title">${esc(t("impact.title", { goal, amount: money(p.remaining) }))}</div>
    <div class="impact-grid">
      <div class="impact-col"><span>${esc(t("impact.now"))}</span><strong>${esc(t("home.per_month", { amount: money(p.now.monthly) }))}</strong>
        <small>${esc(t("impact.reach", { when: when(p.now) }))}</small></div>
      <div class="impact-arrow"><i class="ti ti-arrow-right"></i></div>
      <div class="impact-col plan"><span>${esc(t("impact.plan"))}</span><strong>${esc(t("home.per_month", { amount: money(p.plan.monthly) }))}</strong>
        <small>${esc(t("impact.reach", { when: when(p.plan) }))}</small></div>
    </div>
    ${p.extra_per_month > 0 ? `<p class="small muted">${esc(t("impact.extra", { amount: money(p.extra_per_month) }))}</p>` : ""}`;
}

// ---------- First-visit guide: three steps that show the best of FinAI ----------
const GUIDE_KEY = "finai_guide";

function guideState() {
  try { return JSON.parse(localStorage.getItem(GUIDE_KEY)) || {}; } catch { return {}; }
}

function saveGuide(change) {
  try { localStorage.setItem(GUIDE_KEY, JSON.stringify({ ...guideState(), ...change })); } catch { /* private mode: the guide just isn't remembered */ }
}

function renderGuide() {
  const g = guideState();
  const box = $("#guide");
  if (g.hidden) { box.innerHTML = ""; return; }
  const history = state.history || [];
  const steps = [
    { tab: "spending", icon: "ti-receipt", done: !!g.spending },
    { tab: "goals", icon: "ti-target-arrow", done: history.some((h) => h.type === "saving") },
    { tab: "bills", icon: "ti-calendar-dollar", done: history.some((h) => h.type === "bill") },
  ];
  box.innerHTML = `<div class="card guide">
    <div class="row-between"><h3><i class="ti ti-map-2"></i> ${esc(t("guide.title"))}</h3>
      <button class="icon-btn" id="guide-close" aria-label="${esc(t("guide.close"))}"><i class="ti ti-x"></i></button></div>
    <p class="small muted">${esc(t("guide.intro"))}</p>
    ${steps.map((s, i) => `<button class="guide-step ${s.done ? "done" : ""}" data-guide-tab="${s.tab}">
        <span class="guide-num">${s.done ? '<i class="ti ti-check"></i>' : i + 1}</span>
        <span><strong>${esc(t(`guide.step${i + 1}`))}</strong><small>${esc(t(`guide.step${i + 1}_sub`))}</small></span>
        <i class="ti ti-chevron-right"></i></button>`).join("")}
  </div>`;
  $("#guide-close").onclick = () => { saveGuide({ hidden: true }); renderGuide(); };
  box.querySelectorAll("[data-guide-tab]").forEach((btn) => { btn.onclick = () => showTab(btn.dataset.guideTab); });
}

// The demo account's limit for one payment, in the user's currency (Infinity if unknown).
function payoutMaxHome() {
  const max = state.status && state.status.payout_max;
  const rate = (state.analysis && state.analysis.fx && state.analysis.fx.rate_to_paypal) || 1;
  return max ? max / rate : Infinity;
}

// FinAI's own payouts carry an English note ("FinAI savings: ..."): word it in the user's language.
function txName(tx) {
  if (tx.user_name) return tx.user_name;
  const m = /^FinAI (savings|bill payment): (.+)$/.exec(tx.description || "");
  if (m) return t(m[1] === "savings" ? "history.saved" : "history.paid", { name: itemName({ name: m[2], sample: true }) });
  return tx.display_description;
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
    { colId: "description", headerName: t("col.description"), flex: 1, minWidth: 150, valueGetter: (p) => txName(p.data),
      cellRenderer: (p) => `${esc(p.value)}${p.data.edited ? ` <i class="ti ti-pencil small muted" title="${esc(t("edit.by_you"))}"></i>` : ""}${p.data.pending ? ` <span class="src pending">${esc(t("tag.pending"))}</span>` : ""}${p.data.is_anomaly ? ` <span class="flag" title="${esc(t("tag.unusual"))}">●</span>` : ""}` },
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
  if (txName(tx) !== tx.description) row(t("detail.original_name"), esc(tx.description));
  if (tx.pending) row(t("detail.status"), `<span class="src pending">${esc(t("tag.pending"))}</span> ${esc(t("detail.pending"))}`);
  row(t("col.date"), esc(new Date(tx.date + "T12:00:00").toLocaleDateString(locale(), { weekday: "long", year: "numeric", month: "long", day: "numeric" })));
  row(t("col.category"), `<span class="cat ${type}">${esc(t(`cat.${type}`))}</span>`
    + (tx.edited && tx.claude_category && tx.claude_category !== tx.category
      ? ` <span class="small muted">${esc(t("edit.claude_said", { cat: t(`cat.${tx.claude_category}`) }))}</span>` : ""));
  if (tx.converted || tx.fx_missing) {
    row(t("detail.charged"), `${esc(money(tx.original_amount, tx.original_currency))}${tx.fx_missing ? ` <span class="flag">${t("tag.not_converted")}</span>` : ""}`);
  }
  if (tx.label) row(t("detail.label"), esc(tx.label));
  if (tx.category) row(t("detail.unusual"), tx.is_anomaly ? `<span class="flag">${t("detail.yes")}</span>` : t("detail.no"));
  row(t("detail.source"), sourceTag(tx.source));
  if (tx.reason) rows.push(`<div class="detail-row"><div class="k">${esc(t("detail.reason"))}</div><div class="reason-box"><i class="ti ti-sparkles"></i> ${esc(tx.reason)}</div></div>`);
  row(t("detail.id"), `<span class="small muted">${esc(tx.id)}</span>`);

  const canRecategorize = tx.direction === "out" && tx.kind !== "saving";
  const catOptions = ["need", "want", "luxury"].map((c) =>
    `<option value="${c}" ${tx.category === c ? "selected" : ""}>${esc(capitalize(t(`cat.${c}`)))}</option>`).join("");
  $("#sheet-body").innerHTML = `
    <div class="sheet-amount ${tx.direction === "in" ? "tx-amount in" : ""}">${esc(txAmountText(tx))}</div>
    <div class="sheet-desc">${esc(txName(tx))}${tx.edited ? ` <span class="src edited">${esc(t("edit.by_you"))}</span>` : ""}</div>
    <button class="btn ghost small-btn" id="edit-toggle"><i class="ti ti-pencil"></i> ${esc(t("edit.button"))}</button>
    <form class="edit-box hidden" id="edit-form">
      <label><span>${esc(t("edit.name"))}</span><input name="name" maxlength="80" value="${esc(tx.user_name || "")}" placeholder="${esc(tx.user_name ? txName({ ...tx, user_name: null, display_description: tx.description }) : txName(tx))}"></label>
      ${canRecategorize ? `<label><span>${esc(t("col.category"))}</span><select name="category">${catOptions}</select></label>` : ""}
      <div class="goal-actions">
        <button class="btn" type="submit">${esc(t("edit.save"))}</button>
        ${tx.edited ? `<button class="btn ghost" type="button" id="edit-reset">${esc(t("edit.reset"))}</button>` : ""}
      </div>
      <p class="small muted">${esc(t("edit.help"))}</p>
    </form>
    ${rows.join("")}`;
  $("#edit-toggle").onclick = () => $("#edit-form").classList.toggle("hidden");
  const saveEdit = async (body) => {
    try {
      await api(`/api/transactions/${encodeURIComponent(tx.id)}/edit`, { method: "POST", body });
      await loadAnalysis();
      const updated = state.analysis.transactions.find((x) => x.id === tx.id);
      if (updated) openSheet(updated);
      toast(t("edit.saved"));
    } catch (err) { toast(err.message, true); }
  };
  $("#edit-form").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    // Keep Claude's category unless the user picked a different one.
    const category = f.category && f.category.value !== (tx.claude_category || tx.category) ? f.category.value : "";
    saveEdit({ name: f.name.value.trim(), category });
  };
  if ($("#edit-reset")) $("#edit-reset").onclick = () => saveEdit({ name: "", category: "" });
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
// Claude suggests ONE monthly saving for all goals together. Goals with your own amount keep it
// (it comes out of Claude's total first); the rest is shared out in order, and a goal never gets
// more than it still needs. Same math as budget.claude_shares on the server.
function claudeShares(goals, monthlySaving) {
  const active = goals.filter((g) => Number(g.target) > Number(g.saved || 0));
  let pool = Math.max((monthlySaving || 0) - active.reduce((s, g) => s + (Number(g.monthly) || 0), 0), 0);
  const shares = {};
  for (const g of active) {
    if (Number(g.monthly)) continue;
    shares[g.id] = Math.round(Math.min(pool, Number(g.target) - Number(g.saved || 0)) * 100) / 100;
    pool -= shares[g.id];
  }
  return shares;
}

// The monthly amount used for a goal: your own, or its share of Claude's suggestion.
function goalMonthly(g) {
  return Number(g.monthly) || Number(g.claude_share) || 0;
}

function goalEta(g, monthlySaving) {
  if (g.status === "reached") return t("goals.reached");
  if (g.status === "no_saving" || !g.months) return t("goals.no_saving");
  return t("goals.eta", { amount: money(goalMonthly(g, monthlySaving)), months: g.months, eta: monthName(g.eta) });
}

// Months to reach a goal at `monthly` per month, worked out in the browser so edits feel instant.
function goalPlan(g, monthly) {
  const remaining = Math.max(Number(g.target) - Number(g.saved || 0), 0);
  if (remaining === 0) return { status: "reached", months: 0, eta: null };
  if (!(monthly > 0)) return { status: "no_saving", months: null, eta: null };
  const months = Math.ceil(remaining / monthly);
  const bills = state.billsData || {};
  const thisMonth = bills.today_month || bills.month || new Date().toISOString().slice(0, 7);
  return { status: "on_track", months, eta: shiftMonth(thisMonth, months) };
}

function renderGoalPlan(goals, monthlySaving) {
  const b = state.analysis && state.analysis.budget;
  const active = goals.filter((g) => g.status !== "reached");
  if (!b || !active.length) { $("#goal-plan").innerHTML = ""; return; }
  const planned = active.reduce((sum, g) => sum + goalMonthly(g, monthlySaving), 0);
  const target = b.savings.target;
  const over = planned > target;
  $("#goal-plan").innerHTML = `<div class="goal-plan ${over ? "over" : ""}">
      <div><span class="small muted">${esc(t("goals.plan_total"))}</span><strong>${money(planned)}</strong></div>
      <div><span class="small muted">${esc(t("goals.plan_target", { pct: Math.round(b.percents.savings) }))}</span><strong>${money(target)}</strong></div>
    </div>
    <p class="small ${over ? "over-text" : "muted"}">${esc(t(over ? "goals.plan_over" : "goals.plan_ok", { amount: money(Math.abs(target - planned)) }))}</p>`;
}

function renderGoals(goals, monthlySaving) {
  // Share Claude's amount again (an edit to one goal changes what the others get) and update each ETA.
  const shares = claudeShares(goals, monthlySaving);
  goals.forEach((g) => {
    g.claude_share = shares[g.id] || 0;
    Object.assign(g, goalPlan(g, goalMonthly(g)));
  });
  // What a goal would get if it went back to Claude's suggestion.
  const shareIfReset = (g) => claudeShares(goals.map((x) => (x.id === g.id ? { ...x, monthly: null } : x)), monthlySaving)[g.id] || 0;
  $("#goal-list").innerHTML = goals.length ? goals.map((g) => {
    const pct = g.target > 0 ? Math.min((g.saved / g.target) * 100, 100) : 0;
    return `<div class="goal">
      <div class="bar-label"><strong>${esc(itemName(g))}${g.sample ? " " + sourceTag("sample") : ""}</strong><span>${money(g.saved)} / ${money(g.target)}</span></div>
      <div class="bar"><div style="width:${pct}%;background:var(--primary)"></div></div>
      <div class="tx-meta goal-eta">${esc(goalEta(g, monthlySaving))}
        <span class="src ${g.monthly ? "edited" : "paypal"}">${esc(t(g.monthly ? "goals.monthly_you" : "goals.monthly_claude"))}</span>
        <button class="link-btn" data-edit-monthly="${g.id}">${esc(t("goals.monthly_change"))}</button>
      </div>
      <form class="monthly-form hidden" data-monthly-form="${g.id}">
        <label class="small muted">${esc(t("goals.monthly_label", { currency: state.currency }))}</label>
        <div class="monthly-row">
          <input name="monthly" type="number" min="0" step="0.01" value="${goalMonthly(g, monthlySaving).toFixed(2)}">
          <button class="btn" type="submit">${esc(t("edit.save"))}</button>
          ${g.monthly ? `<button class="btn ghost" type="button" data-monthly-reset="${g.id}">${esc(t("goals.monthly_reset", { amount: money(shareIfReset(g)) }))}</button>` : ""}
        </div>
        <div class="small muted" data-monthly-preview="${g.id}"></div>
      </form>
      <div class="goal-actions">
        <button class="btn" data-contribute="${g.id}"><i class="ti ti-arrow-up-right"></i> ${t("goals.transfer")}</button>
        <button class="btn danger" data-delete-goal="${g.id}">${t("goals.delete")}</button>
      </div>
    </div>`;
  }).join("") : `<p class="muted">${t("goals.empty")}</p>`;

  renderGoalPlan(goals, monthlySaving);
  document.querySelectorAll("[data-contribute]").forEach((btn) => {
    btn.onclick = () => {
      const goal = goals.find((g) => g.id === btn.dataset.contribute);
      contribute(goal, goalMonthly(goal, monthlySaving));
    };
  });
  document.querySelectorAll("[data-edit-monthly]").forEach((btn) => {
    btn.onclick = () => document.querySelector(`[data-monthly-form="${btn.dataset.editMonthly}"]`).classList.toggle("hidden");
  });
  const saveMonthly = async (goal, monthly) => {
    try {
      const saved = await api(`/api/goals/${goal.id}`, { method: "PATCH", body: { monthly } });
      Object.assign(goal, saved, goalPlan(saved, goalMonthly(saved, monthlySaving)));
      renderGoals(goals, monthlySaving);
      toast(t("goals.monthly_saved"));
    } catch (err) { toast(err.message, true); }
  };
  document.querySelectorAll("[data-monthly-form]").forEach((form) => {
    const goal = goals.find((g) => g.id === form.dataset.monthlyForm);
    const preview = form.querySelector("[data-monthly-preview]");
    form.monthly.oninput = () => {
      const plan = goalPlan(goal, parseFloat(form.monthly.value) || 0);
      preview.textContent = plan.months ? t("goals.monthly_preview", { months: plan.months, eta: monthName(plan.eta) }) : "";
    };
    form.onsubmit = (e) => { e.preventDefault(); saveMonthly(goal, parseFloat(form.monthly.value) || 0); };
    const reset = form.querySelector("[data-monthly-reset]");
    if (reset) reset.onclick = () => saveMonthly(goal, 0);
  });
  document.querySelectorAll("[data-delete-goal]").forEach((btn) => {
    btn.onclick = async () => {
      const ok = await confirmDialog({ title: t("goals.delete_title"), body: esc(t("goals.delete_body")), okText: t("goals.delete") });
      if (!ok) return;
      await api(`/api/goals/${btn.dataset.deleteGoal}`, { method: "DELETE" });
      state.analysis.goals = state.analysis.goals.filter((g) => g.id !== btn.dataset.deleteGoal);
      renderGoals(state.analysis.goals, monthlySaving);
      refreshInBackground();
    };
  });
}

async function contribute(goal, suggested) {
  // The demo account sends at most payout_max per payment: start at that amount if the
  // suggestion is bigger, and say why.
  const max = payoutMaxHome();
  const start = Math.min(suggested || 0, Math.floor(max * 100) / 100);
  const limitNote = Number.isFinite(max)
    ? `<p class="small muted">${esc(t("pay.demo_limit", { amount: money(max) }))}</p>` : "";
  const pending = confirmDialog({
    title: t("goals.transfer_title", { goal: itemName(goal) }),
    body: t("goals.transfer_body"),
    extraHtml: `<label class="small muted">${esc(t("goals.amount", { currency: state.currency }))}</label>
      <input id="contrib-amount" type="number" min="0.01" step="0.01" max="${Number.isFinite(max) ? max.toFixed(2) : ""}" value="${start.toFixed(2)}">
      ${limitNote}<div id="contrib-fx">${payoutNote(start)}</div>`,
    okText: t("goals.confirm"),
  });
  $("#contrib-amount").oninput = (e) => { $("#contrib-fx").innerHTML = payoutNote(parseFloat(e.target.value) || 0); };
  const ok = await pending;
  if (!ok) return;
  const amount = parseFloat($("#contrib-amount").value);
  try {
    const res = await api(`/api/goals/${goal.id}/contribute`, { method: "POST", body: { amount, confirm: true } });
    toast(t("goals.sent", { amount: money(amount), batch: res.payout.payout_batch_id, status: res.payout.status }));
    await Promise.all([loadAnalysis(), loadHistory()]);  // fast: Claude isn't asked again for a pending payout
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadHistory() {
  state.history = await api("/api/history");
  renderHistory();
}

function renderHistory() {
  const all = state.history || [];
  $("#history-list").innerHTML = historyHtml(all.filter((h) => h.type === "saving"), t("history.empty"));
  $("#bill-history-list").innerHTML = historyHtml(all.filter((h) => h.type === "bill"), t("bills.history_empty"));
  renderGuide();  // a transfer or a bill payment checks off a guide step
}

function historyHtml(items, emptyText) {
  return items.length ? items.map((h) => {
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
  }).join("") : esc(emptyText);
}

// ---------- Bills, recurring payments and calendar ----------
async function loadBills() {
  state.billsData = await api("/api/bills");
  if (!state.calMonth || state.calMonth === state.billsData.month) {
    state.calMonth = state.billsData.month;
    state.calData = state.billsData;
  } else {
    state.calData = await api(`/api/bills?month=${state.calMonth}`);
  }
  renderBills();
}

function monthsBetween(from, to) {
  const [y1, m1] = from.split("-").map(Number);
  const [y2, m2] = to.split("-").map(Number);
  return (y2 - y1) * 12 + (m2 - m1);
}

function shiftMonth(key, delta) {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

async function moveCalendar(delta) {
  const target = shiftMonth(state.calMonth, delta);
  $("#calendar").classList.add("busy");
  try {
    state.calData = target === state.billsData.month ? state.billsData : await api(`/api/bills?month=${target}`);
    state.calMonth = target;
    renderCalendar(state.calData);
  } catch (err) { toast(err.message, true); } finally { $("#calendar").classList.remove("busy"); }
}

// Recurring payments come from transaction descriptions: show them in the user's language.
function recurringName(r) {
  const tx = state.analysis && state.analysis.transactions.find((x) => x.description === r.name);
  return tx ? tx.display_description : r.name;
}

function renderBills() {
  const data = state.billsData;
  if (!data.month) return;
  renderCalendar(state.calData || data);
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
  const isPast = data.month < data.today_month;
  $("#cal-title").textContent = capitalize(monthName(data.month));
  $("#cal-today").classList.toggle("hidden", data.month === data.today_month);

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
        const cls = x.paidOn ? "paid" : isPast ? "missed" : x.auto ? "auto" : "";
        const title = `${x.name} ${money(x.amount)}${x.paidOn ? " · " + t("bills.paid_on", { date: shortDate(x.paidOn) }) : ""}`;
        return `<div class="cal-item ${cls}" title="${esc(title)}">${x.paidOn ? "✓ " : ""}${esc(x.name)}</div>`;
      }).join("")}
    </div>`;
  }
  $("#calendar").innerHTML = html;

  const pending = items.filter((x) => !x.paidOn);
  const paid = items.filter((x) => x.paidOn);
  const sum = (list) => list.reduce((s, x) => s + Number(x.amount), 0);
  let summary = "";
  if (isPast && !data.has_data) summary = t("bills.no_data");
  else if (isPast) summary = t("bills.paid_summary", { count: paid.length, amount: money(sum(paid)) });
  else if (items.length) summary = t("bills.pending", { count: pending.length, amount: money(sum(pending)) });
  $("#bills-summary").textContent = summary;
}

function renderBillList(bills) {
  const sorted = [...bills].sort((a, b) => a.day - b.day);
  $("#bill-list").innerHTML = sorted.length ? sorted.map((b) => {
    const paidBadge = b.paid_on
      ? `<span class="badge ok" title="${b.paid_in_paypal ? esc(t("bills.paid_paypal_help")) : ""}">${esc(t("bills.paid_on", { date: shortDate(b.paid_on) }))}</span>` : "";
    // Bills above the demo limit can't be paid from the shared test account: say so up front.
    const overLimit = !paidBadge && Number(b.amount) > payoutMaxHome() + 0.005;
    const payButton = overLimit
      ? `<button class="btn" disabled title="${esc(t("pay.demo_limit", { amount: money(payoutMaxHome()) }))}">${t("bills.pay")}</button>`
      : `<button class="btn" data-pay="${b.id}">${t("bills.pay")}</button>`;
    return `<div class="bill">
      <div class="bill-main"><div class="bill-icon"><i class="ti ti-file-invoice"></i></div>
        <div><strong>${esc(itemName(b))}</strong>${b.sample ? " " + sourceTag("sample") : ""}<div class="tx-meta">${esc(t("bills.day_line", { day: b.day, amount: money(b.amount) }))}</div>
        ${overLimit ? `<div class="tx-meta limit-note">${esc(t("pay.over_limit", { amount: money(payoutMaxHome()) }))}</div>` : ""}</div></div>
      <div class="goal-actions" style="margin:0">
        ${paidBadge || payButton}
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

// ---------- Refresh: pull down on a phone, or the button at the top ----------
let refreshing = false;

async function refreshAll() {
  if (refreshing) return;
  refreshing = true;
  const ptr = $("#ptr");
  ptr.className = "ptr loading";
  ptr.querySelector("i").className = "ti ti-refresh";
  ptr.querySelector("span").textContent = t("refresh.loading");
  $("#btn-top-refresh").classList.add("spin");
  try {
    await Promise.all([loadAnalysis(), loadBills(), loadHistory()]);
    toast(t("refresh.done"));
  } catch (err) {
    toast(err.message, true);
  } finally {
    refreshing = false;
    ptr.className = "ptr";
    ptr.style.height = "";
    ptr.querySelector("i").className = "ti ti-arrow-down";
    $("#btn-top-refresh").classList.remove("spin");
  }
}

// Updates Claude's part without blocking the screen (e.g. after adding a goal, which Claude
// takes into account: a new analysis can take a minute).
function refreshInBackground() {
  $("#ai-mode").textContent = t("home.updating");
  loadAnalysis().catch((err) => toast(err.message, true));
}

function wirePullToRefresh() {
  const ptr = $("#ptr");
  const label = ptr.querySelector("span");
  const PULL = 80;  // how far (px) to pull before releasing refreshes
  let startY = null, dy = 0;
  const blocked = () => refreshing || $("#sheet").classList.contains("open") || !$("#modal").classList.contains("hidden");
  window.addEventListener("touchstart", (e) => {
    startY = window.scrollY <= 0 && !blocked() ? e.touches[0].clientY : null;
    dy = 0;
  }, { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (startY === null) return;
    dy = e.touches[0].clientY - startY;
    if (dy <= 0) { ptr.style.height = ""; return; }
    ptr.style.height = `${Math.min(dy * 0.5, 64)}px`;
    const ready = dy >= PULL;
    ptr.classList.toggle("ready", ready);
    label.textContent = t(ready ? "refresh.release" : "refresh.pull");
  }, { passive: true });
  window.addEventListener("touchend", () => {
    if (startY === null) return;
    startY = null;
    if (dy >= PULL) refreshAll();
    else { ptr.style.height = ""; ptr.className = "ptr"; }
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
  $("#btn-reset").onclick = async () => {
    const ok = await confirmDialog({ title: t("demo.reset_title"), body: t("demo.reset_body"), okText: t("demo.reset") });
    if (!ok) return;
    showLoading("loading.default");
    try {
      await api("/api/reset", { method: "POST", body: {} });
      location.reload();  // start fresh, exactly like a first visit
    } catch (err) { hideLoading(); toast(err.message, true); }
  };
  $("#goal-form").onsubmit = async (e) => {
    e.preventDefault();
    const button = e.target.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const goal = await api("/api/goals", { method: "POST", body: formData(e.target) });
      e.target.reset();
      // Show it right away; Claude's estimate for it arrives in the background.
      const suggested = (state.analysis && state.analysis.suggested_monthly_saving) || 0;
      state.analysis.goals.push({ ...goal, ...goalPlan(goal, goalMonthly(goal, suggested)) });
      renderGoals(state.analysis.goals, suggested);
      toast(t("goals.added"));
      refreshInBackground();
    } catch (err) { toast(err.message, true); } finally { button.disabled = false; }
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
  wirePullToRefresh();
  $("#btn-top-refresh").onclick = refreshAll;
  $("#score-pill").onclick = () => {
    const open = $("#health-detail").hidden;
    $("#health-detail").hidden = !open;
    $("#score-pill").setAttribute("aria-expanded", String(open));
  };
  $("#cal-prev").onclick = () => moveCalendar(-1);
  $("#cal-next").onclick = () => moveCalendar(1);
  $("#cal-today").onclick = () => moveCalendar(0 - monthsBetween(state.billsData.month, state.calMonth));
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
