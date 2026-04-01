function setPeriodLabel() {
  const el = $("#period-label");
  if (!el) return;
  el.textContent = new Date().toLocaleString("zh-CN", {
    year: "numeric",
    month: "long",
  });
}

function fmtMoney(n) {
  return (
    "¥" +
    Number(n).toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleString("zh-CN", { hour12: false });
}

function fmtDate(ymd) {
  if (!ymd) return "";
  const d = new Date(`${ymd}T00:00:00`);
  if (isNaN(d.getTime())) return ymd;
  return d.toLocaleDateString("zh-CN");
}

const state = {
  startDate: "",
  endDate: "",
  panelOpen: false,
  sourceMode: "overall",
  sourceData: { overall: null, filtered: null },
};

function isAddSheetLayout() {
  return window.matchMedia("(max-width: 1099px)").matches;
}

/** 窄屏下「新增一笔」底部抽屉；宽屏无效 */
function setAddSheetOpen(open) {
  const app = $("#view-app");
  const backdrop = $("#add-sheet-backdrop");
  if (!app || !backdrop) return;
  if (!isAddSheetLayout()) {
    app.classList.remove("add-sheet-open");
    backdrop.classList.add("hidden");
    backdrop.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    return;
  }
  const on = Boolean(open);
  if (on) setPanelOpen(false);
  app.classList.toggle("add-sheet-open", on);
  backdrop.classList.toggle("hidden", !on);
  backdrop.setAttribute("aria-hidden", on ? "false" : "true");
  document.body.style.overflow = on ? "hidden" : "";
}

function toggleAddSheet() {
  const app = $("#view-app");
  if (!app?.classList.contains("add-sheet-open")) setAddSheetOpen(true);
  else setAddSheetOpen(false);
}

function buildQuery() {
  const p = new URLSearchParams();
  if (state.startDate && state.endDate) {
    p.set("start_date", state.startDate);
    p.set("end_date", state.endDate);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

function setDefaultTransactedOn() {
  const el = $("#input-transacted-on");
  if (!el) return;
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  el.value = `${yyyy}-${mm}-${dd}`;
}

function groupByYearMonth(list) {
  const m = new Map();
  for (const tx of list) {
    const key = (tx.transacted_on || "").slice(0, 7);
    if (!m.has(key)) m.set(key, []);
    m.get(key).push(tx);
  }
  return [...m.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
}

function calcGroupSummary(items) {
  let exp = 0;
  let inc = 0;
  for (const tx of items) {
    if (tx.type === "expense") exp += Number(tx.amount);
    else inc += Number(tx.amount);
  }
  return { exp, inc, net: inc - exp, count: items.length };
}

function renderGroupedList(list) {
  const ul = $("#tx-list");
  ul.innerHTML = "";
  const grouped = groupByYearMonth(list);
  for (const [ym, items] of grouped) {
    const block = document.createElement("li");
    block.className = "tx-group";
    const [y, m] = ym.split("-");
    const s = calcGroupSummary(items);
    block.innerHTML = `
      <div class="tx-group-head">
        <strong>${escapeHtml(y)}年${escapeHtml(String(Number(m)))}月</strong>
        <span>共 ${s.count} 笔 · 支出 ${fmtMoney(s.exp)} · 收入 ${fmtMoney(s.inc)} · 净值 ${fmtMoney(s.net)}</span>
      </div>
      <ul class="tx-sub-list"></ul>
    `;
    const sub = block.querySelector(".tx-sub-list");
    for (const tx of items) sub.appendChild(renderTx(tx));
    ul.appendChild(block);
  }
}

function toYmd(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function setFilterToCurrentMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  state.startDate = toYmd(first);
  state.endDate = toYmd(last);
  const sd = $("#filter-start-date");
  const ed = $("#filter-end-date");
  if (sd) sd.value = state.startDate;
  if (ed) ed.value = state.endDate;
  updateDateTriggerText();
}

function setQuickRange(months) {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - Number(months));
  start.setDate(start.getDate() + 1);
  state.startDate = toYmd(start);
  state.endDate = toYmd(end);
  const sd = $("#filter-start-date");
  const ed = $("#filter-end-date");
  if (sd) sd.value = state.startDate;
  if (ed) ed.value = state.endDate;
  updateDateTriggerText();
}

function setQuickRangeActive(months) {
  document.querySelectorAll(".btn-quick-range").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.months === String(months));
  });
}

function updateDateTriggerText() {
  const el = $("#date-trigger-text");
  if (!el) return;
  if (state.startDate && state.endDate) {
    el.textContent = `${state.startDate} ~ ${state.endDate}`;
  } else {
    el.textContent = "选择日期范围";
  }
}

function setPanelOpen(open) {
  state.panelOpen = open;
  const panel = $("#date-panel");
  if (!panel) return;
  panel.classList.toggle("hidden", !open);
  if (open) setAddSheetOpen(false);
}

function sourceModeLabel(mode) {
  return mode === "filtered" ? "当前筛选" : "总体";
}

function setSourceTabs() {
  $("#source-tab-overall")?.classList.toggle("active", state.sourceMode === "overall");
  $("#source-tab-filtered")?.classList.toggle("active", state.sourceMode === "filtered");
}

function renderSourceModal() {
  const payload = state.sourceData[state.sourceMode];
  const topList = $("#source-top-list");
  const yearList = $("#source-year-list");
  if (!topList || !yearList) return;
  if (!payload || !Array.isArray(payload.groups)) {
    topList.innerHTML = "<li>暂无数据</li>";
    yearList.innerHTML = "";
    return;
  }

  const search = ($("#source-search")?.value || "").trim();
  const groups = payload.groups.filter((g) => {
    const ym = `${g.year}-${String(g.month).padStart(2, "0")}`;
    if (!search) return true;
    return ym.includes(search) || String(g.year).includes(search);
  });

  const top = [...groups]
    .sort((a, b) => Math.abs(b.net) - Math.abs(a.net))
    .slice(0, 5);
  topList.innerHTML = top.length
    ? top
        .map(
          (g) =>
            `<li><strong>${g.year}-${String(g.month).padStart(2, "0")}</strong> · 收入 ${fmtMoney(
              g.total_income
            )} · 支出 ${fmtMoney(g.total_expense)} · 净值 ${fmtMoney(g.net)}（${g.count} 笔）</li>`
        )
        .join("")
    : "<li>无匹配月份</li>";

  const byYear = new Map();
  for (const g of groups) {
    const y = String(g.year);
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y).push(g);
  }
  const years = [...byYear.keys()].sort((a, b) => (a < b ? 1 : -1));
  yearList.innerHTML = years
    .map((y) => {
      const rows = byYear.get(y);
      const exp = rows.reduce((s, r) => s + Number(r.total_expense), 0);
      const inc = rows.reduce((s, r) => s + Number(r.total_income), 0);
      const net = inc - exp;
      const rid = `year-${y}`;
      return `
        <div class="source-year-block">
          <button type="button" class="source-year-head" data-target="${rid}">
            <span><strong>${y}年</strong> · 收入 ${fmtMoney(inc)} · 支出 ${fmtMoney(exp)} · 净值 ${fmtMoney(net)}</span>
            <span class="material-symbols-outlined">expand_more</span>
          </button>
          <div id="${rid}" class="source-months hidden">
            ${rows
              .sort((a, b) => b.month - a.month)
              .map(
                (r) =>
                  `<div class="source-month-row">${r.year}-${String(r.month).padStart(2, "0")} · 收入 ${fmtMoney(
                    r.total_income
                  )} · 支出 ${fmtMoney(r.total_expense)} · 净值 ${fmtMoney(r.net)}（${r.count} 笔）</div>`
              )
              .join("")}
          </div>
        </div>
      `;
    })
    .join("");
}

async function loadSourceData(mode) {
  if (state.sourceData[mode]) return;
  const q = mode === "filtered" ? buildQuery() : "";
  state.sourceData[mode] = await api(`/api/transactions/grouped${q}`);
}

async function openSourceModal(mode = "overall") {
  setAddSheetOpen(false);
  state.sourceMode = mode;
  setSourceTabs();
  await loadSourceData(mode);
  renderSourceModal();
  const sm = $("#source-modal");
  if (sm) {
    sm.classList.remove("hidden");
    sm.setAttribute("aria-hidden", "false");
  }
}

function closeSourceModal() {
  const sm = $("#source-modal");
  if (sm) {
    sm.classList.add("hidden");
    sm.setAttribute("aria-hidden", "true");
  }
}

function showApp(me) {
  setAddSheetOpen(false);
  $("#view-login").classList.add("hidden");
  $("#view-app").classList.remove("hidden");
  $("#whoami").textContent = `${me.username}（${me.role === "admin" ? "管理员" : "用户"}）`;
  $("#link-admin").classList.toggle("hidden", me.role !== "admin");
  setPeriodLabel();
}

function showLogin() {
  setAddSheetOpen(false);
  $("#view-app").classList.add("hidden");
  $("#view-login").classList.remove("hidden");
  $("#link-admin").classList.add("hidden");
}

async function refresh() {
  const q = buildQuery();
  const [summary, list] = await Promise.all([
    api(`/api/summary${q}`),
    api(`/api/transactions${q}`),
  ]);
  $("#sum-expense").textContent = fmtMoney(summary.total_expense);
  $("#sum-income").textContent = fmtMoney(summary.total_income);
  const netEl = $("#sum-net");
  netEl.textContent = fmtMoney(summary.net);
  netEl.classList.toggle("negative", summary.net < 0);
  $("#sum-overall-expense").textContent = fmtMoney(summary.overall_expense);
  $("#sum-overall-income").textContent = fmtMoney(summary.overall_income);
  const overallNet = $("#sum-overall-net");
  overallNet.textContent = fmtMoney(summary.overall_net);
  overallNet.classList.toggle("negative", summary.overall_net < 0);

  const emptyWrap = $("#empty-wrap");
  emptyWrap.classList.toggle("hidden", list.length > 0);
  const emptyText = $("#empty-text");
  if (emptyText) {
    emptyText.textContent =
      summary.has_filter
        ? "当前年份月份范围内暂无记录，可调整筛选或新增交易。"
        : "还没有任何记录，点击右下角加号填写金额、日期与说明即可新增。";
  }
  renderGroupedList(list);
  state.sourceData.overall = null;
  state.sourceData.filtered = null;
}

function renderTx(tx) {
  const li = document.createElement("li");
  li.className = "tx-item";
  li.dataset.id = String(tx.id);

  const head = document.createElement("div");
  head.className = "tx-head";
  head.innerHTML = `
    <span class="badge ${tx.type}">${tx.type === "expense" ? "消费" : "收入"}</span>
    <div class="tx-main">
      <div class="tx-amt">${fmtMoney(tx.amount)}</div>
      <div class="tx-note-preview">${escapeHtml(tx.note || "—")}</div>
    </div>
    <span class="material-symbols-outlined tx-chev">chevron_right</span>
  `;

  const body = document.createElement("div");
  body.className = "tx-body";
  body.innerHTML = `
    <p class="tx-meta">交易日期：${escapeHtml(fmtDate(tx.transacted_on))}</p>
    <p class="tx-meta">创建：${escapeHtml(fmtTime(tx.created_at))}
      ${tx.updated_at !== tx.created_at ? ` · 更新：${escapeHtml(fmtTime(tx.updated_at))}` : ""}</p>
    ${billMetaHtml(tx)}
    <div class="field">
      <span>补充说明</span>
      <textarea class="edit-note" rows="2">${escapeHtml(tx.note || "")}</textarea>
    </div>
    <div class="field">
      <span>金额（元）</span>
      <input type="number" class="edit-amt" step="0.01" min="0.01" value="${escapeAttr(String(tx.amount))}" />
    </div>
    <div class="tx-actions">
      <button type="button" class="btn btn-primary btn-save" style="text-transform:none; letter-spacing:0;">保存修改</button>
      <button type="button" class="btn btn-danger btn-del">删除</button>
    </div>
  `;

  const chev = head.querySelector(".tx-chev");
  head.addEventListener("click", () => {
    li.classList.toggle("open");
    chev.classList.toggle("rotate", li.classList.contains("open"));
  });

  body.querySelector(".btn-save").addEventListener("click", async (e) => {
    e.stopPropagation();
    const note = body.querySelector(".edit-note").value;
    const amount = parseFloat(body.querySelector(".edit-amt").value);
    if (!(amount > 0)) {
      toast("金额须为大于 0 的数字", true);
      return;
    }
    try {
      await api(`/api/transactions/${tx.id}`, {
        method: "PATCH",
        body: JSON.stringify({ note, amount }),
      });
      toast("已保存");
      await refresh();
    } catch (err) {
      toast(err.message, true);
    }
  });

  body.querySelector(".btn-del").addEventListener("click", async (e) => {
    e.stopPropagation();
    setAddSheetOpen(false);
    const ok = await window.confirmDialog({
      title: "删除记录",
      message: "确定删除这条记录？删除后无法恢复。",
      confirmText: "删除",
      cancelText: "取消",
      danger: true,
    });
    if (!ok) return;
    try {
      await api(`/api/transactions/${tx.id}`, { method: "DELETE" });
      toast("已删除");
      await refresh();
    } catch (err) {
      toast(err.message, true);
    }
  });

  li.appendChild(head);
  li.appendChild(body);
  return li;
}

function billMetaHtml(tx) {
  if (!tx.import_platform) return "";
  const plat = tx.import_platform === "alipay" ? "支付宝" : "微信";
  const rows = [
    ["导入来源", plat],
    ["外部单号", tx.external_id],
    ["分类/类型", tx.bill_category],
    ["交易对方", tx.bill_counterparty],
    ["商品说明", tx.bill_product],
    ["支付方式", tx.bill_payment_method],
    ["商户单号", tx.bill_merchant_no],
    ["导出备注", tx.bill_export_note],
  ].filter(([, v]) => v != null && String(v).trim() !== "");
  if (!rows.length) {
    return `<p class="tx-meta tx-bill-ctx">${escapeHtml(plat)}导入</p>`;
  }
  return `<div class="tx-bill-block" aria-label="账单导入字段">
    <p class="tx-meta tx-bill-title">${escapeHtml(plat)}导入明细</p>
    <ul class="tx-bill-list">
      ${rows
        .map(
          ([k, v]) =>
            `<li><span class="tx-bill-k">${escapeHtml(k)}</span> ${escapeHtml(String(v))}</li>`
        )
        .join("")}
    </ul>
  </div>`;
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: fd.get("username"),
        password: fd.get("password"),
      }),
    });
    const me = await api("/api/me");
    showApp(me);
    await refresh();
    toast("登录成功");
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-logout").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    showLogin();
    toast("已登出");
  } catch (err) {
    toast(err.message, true);
  }
});

function openImportModal() {
  setAddSheetOpen(false);
  const m = $("#import-modal");
  if (m) {
    m.classList.remove("hidden");
    m.setAttribute("aria-hidden", "false");
  }
  updateImportFileAccept();
}

function closeImportModal() {
  const m = $("#import-modal");
  if (m) {
    m.classList.add("hidden");
    m.setAttribute("aria-hidden", "true");
  }
  const fin = $("#import-file");
  if (fin) {
    fin.value = "";
    const nameEl = $("#import-file-name");
    if (nameEl) nameEl.textContent = "未选择文件";
  }
}

$("#btn-import-open")?.addEventListener("click", () => {
  openImportModal();
});

$("#import-modal-close")?.addEventListener("click", () => {
  closeImportModal();
});

$("#import-modal-backdrop")?.addEventListener("click", () => {
  closeImportModal();
});

$("#import-file")?.addEventListener("change", (e) => {
  const nameEl = $("#import-file-name");
  if (nameEl) {
    const files = e.target.files;
    nameEl.textContent = files && files[0] ? files[0].name : "未选择文件";
  }
});

function updateImportFileAccept() {
  const sel = $("#import-platform");
  const fin = $("#import-file");
  if (!sel || !fin) return;
  fin.accept = sel.value === "alipay" ? ".csv,text/csv" : ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
}

$("#import-platform")?.addEventListener("change", updateImportFileAccept);
updateImportFileAccept();

$("#btn-import")?.addEventListener("click", async () => {
  const plat = ($("#import-platform")?.value || "").trim();
  const fin = $("#import-file");
  if (!fin || !fin.files || !fin.files[0]) {
    toast("请选择要导入的文件", true);
    return;
  }
  const fd = new FormData();
  fd.append("platform", plat);
  fd.append("file", fin.files[0], fin.files[0].name);
  try {
    const r = await fetch("/api/transactions/import", {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    const text = await r.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text || r.statusText };
    }
    if (!r.ok) {
      const msg = data?.detail || r.statusText;
      throw new Error(
        Array.isArray(msg) ? msg.map((m) => m.msg || m).join("; ") : String(msg)
      );
    }
    toast(
      `导入完成：新增 ${data.inserted} 条，跳过重复 ${data.skipped_duplicate}，不计/状态等已跳过行见服务端统计。`
    );
    closeImportModal();
    await refresh();
  } catch (err) {
    toast(err.message, true);
  }
});

$("#form-add").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const type = fd.get("type_in");
  const amount = parseFloat(fd.get("amount"));
  const note = (fd.get("note") || "").toString();
  const transacted_on = (fd.get("transacted_on") || "").toString();
  if (!(amount > 0)) {
    toast("请输入大于 0 的金额", true);
    return;
  }
  try {
    await api("/api/transactions", {
      method: "POST",
      body: JSON.stringify({ type, amount, note, transacted_on }),
    });
    e.target.reset();
    e.target.querySelector('input[name="type_in"][value="expense"]').checked =
      true;
    setDefaultTransactedOn();
    toast("已记入");
    setAddSheetOpen(false);
    await refresh();
  } catch (err) {
    toast(err.message, true);
  }
});

(async function boot() {
  try {
    const me = await api("/api/me");
    showApp(me);
    setDefaultTransactedOn();
    setFilterToCurrentMonth();
    updateDateTriggerText();
    await refresh();
  } catch {
    showLogin();
    setDefaultTransactedOn();
  }
})();

$("#filter-apply")?.addEventListener("click", async () => {
  const sd = $("#filter-start-date")?.value || "";
  const ed = $("#filter-end-date")?.value || "";
  if (!sd || !ed) {
    toast("请选择开始和结束日期", true);
    return;
  }
  if (sd > ed) {
    toast("开始日期不能晚于结束日期", true);
    return;
  }
  state.startDate = sd;
  state.endDate = ed;
  setQuickRangeActive("");
  updateDateTriggerText();
  setPanelOpen(false);
  await refresh();
});

document.querySelectorAll(".btn-quick-range").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const months = btn.dataset.months || "1";
    setQuickRange(months);
    setQuickRangeActive(months);
    setPanelOpen(false);
    await refresh();
  });
});

$("#filter-reset")?.addEventListener("click", async () => {
  setFilterToCurrentMonth();
  setQuickRangeActive("");
  setPanelOpen(false);
  await refresh();
});

$("#btn-source-locate")?.addEventListener("click", async () => {
  await openSourceModal("overall");
});

$("#source-tab-overall")?.addEventListener("click", async () => {
  await openSourceModal("overall");
});

$("#source-tab-filtered")?.addEventListener("click", async () => {
  await openSourceModal("filtered");
});

$("#source-search")?.addEventListener("input", () => {
  renderSourceModal();
});

$("#source-modal-close")?.addEventListener("click", () => {
  closeSourceModal();
});

$("#source-modal-backdrop")?.addEventListener("click", () => {
  closeSourceModal();
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".source-year-head");
  if (!btn) return;
  const target = document.getElementById(btn.dataset.target || "");
  if (!target) return;
  target.classList.toggle("hidden");
});

$("#btn-date-panel")?.addEventListener("click", (e) => {
  e.stopPropagation();
  setPanelOpen(!state.panelOpen);
});

$("#filter-cancel")?.addEventListener("click", () => {
  const sd = $("#filter-start-date");
  const ed = $("#filter-end-date");
  if (sd) sd.value = state.startDate;
  if (ed) ed.value = state.endDate;
  setPanelOpen(false);
});

window.addEventListener("resize", () => {
  if (!isAddSheetLayout()) setAddSheetOpen(false);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const confirmEl = $("#confirm-modal");
  if (confirmEl && !confirmEl.classList.contains("hidden")) return;
  const app = $("#view-app");
  if (app?.classList.contains("add-sheet-open")) {
    e.preventDefault();
    setAddSheetOpen(false);
  }
});

$("#btn-add-fab")?.addEventListener("click", () => {
  toggleAddSheet();
});

$("#btn-add-sheet-close")?.addEventListener("click", () => {
  setAddSheetOpen(false);
});

$("#add-sheet-backdrop")?.addEventListener("click", () => {
  setAddSheetOpen(false);
});

document.body.addEventListener("click", (e) => {
  if (
    state.panelOpen &&
    !e.target.closest("#date-panel") &&
    !e.target.closest("#btn-date-panel")
  ) {
    setPanelOpen(false);
  }
});
