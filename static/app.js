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
  keyword: "",
  txPage: 1,
  txTotal: 0,
  txItems: [],
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

function buildTxQuery(page = 1, pageSize = 50) {
  const p = new URLSearchParams();
  if (state.startDate && state.endDate) {
    p.set("start_date", state.startDate);
    p.set("end_date", state.endDate);
  }
  const kw = (state.keyword || "").trim();
  if (kw) p.set("keyword", kw);
  p.set("page", String(page));
  p.set("page_size", String(pageSize));
  return `?${p.toString()}`;
}

function updateLoadMoreUI() {
  const wrap = $("#tx-list-more-wrap");
  const btn = $("#btn-load-more");
  const hint = $("#tx-list-count-hint");
  if (!wrap || !btn || !hint) return;
  const hasRows = state.txTotal > 0;
  wrap.classList.toggle("hidden", !hasRows);
  const hasMore = state.txItems.length < state.txTotal;
  btn.classList.toggle("hidden", !hasMore);
  hint.textContent = `已加载 ${state.txItems.length} / ${state.txTotal} 条`;
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

async function refresh(opts = { busy: true }) {
  const q = buildQuery();
  const tq = buildTxQuery(1, 50);
  if (opts.busy) beginBusy();
  try {
    const [summary, txPayload] = await Promise.all([
      api(`/api/summary${q}`),
      api(`/api/transactions${tq}`),
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

    state.txTotal = txPayload.total;
    state.txPage = 1;
    state.txItems = txPayload.items;

    const emptyWrap = $("#empty-wrap");
    emptyWrap.classList.toggle("hidden", state.txTotal > 0);
    const emptyText = $("#empty-text");
    if (emptyText) {
      const kw = (state.keyword || "").trim();
      if (kw) {
        emptyText.textContent =
          "没有匹配当前关键词的交易，可修改搜索词或调整日期范围。";
      } else if (summary.has_filter) {
        emptyText.textContent =
          "当前日期范围内暂无记录，可调整筛选或新增交易。";
      } else {
        emptyText.textContent =
          "还没有任何记录，点击右下角加号填写金额、日期与说明即可新增。";
      }
    }
    renderGroupedList(state.txItems);
    updateLoadMoreUI();
    state.sourceData.overall = null;
    state.sourceData.filtered = null;
  } finally {
    if (opts.busy) endBusy();
  }
}

function renderTx(tx) {
  const li = document.createElement("li");
  li.className = "tx-item";
  li.dataset.id = String(tx.id);
  const typeName = `edit_type_${tx.id}`;

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
    <p class="tx-meta">创建：${escapeHtml(fmtTime(tx.created_at))}
      ${tx.updated_at !== tx.created_at ? ` · 更新：${escapeHtml(fmtTime(tx.updated_at))}` : ""}</p>
    ${billMetaHtml(tx)}
    <div class="field">
      <span>类型</span>
      <div class="type-pill-wrap" role="group" aria-label="收支类型">
        <label>
          <input type="radio" name="${typeName}" value="expense" ${tx.type === "expense" ? "checked" : ""} />
          <span>消费</span>
        </label>
        <label>
          <input type="radio" name="${typeName}" value="income" ${tx.type === "income" ? "checked" : ""} />
          <span>收入</span>
        </label>
      </div>
    </div>
    <div class="field">
      <span>交易日期</span>
      <input type="date" class="edit-date" value="${escapeAttr(tx.transacted_on || "")}" />
    </div>
    <div class="field">
      <span>补充说明</span>
      <textarea class="edit-note" rows="2">${escapeHtml(tx.note || "")}</textarea>
    </div>
    <div class="field">
      <span>金额（元）</span>
      <input type="number" class="edit-amt" step="0.01" min="0.01" value="${escapeAttr(String(tx.amount))}" />
    </div>
    <div class="tx-actions">
      <button type="button" class="btn btn-primary btn-save btn-loading" style="text-transform:none; letter-spacing:0;">保存修改</button>
      <button type="button" class="btn btn-danger btn-del btn-loading">删除</button>
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
    const type = body.querySelector(`input[name="${typeName}"]:checked`)?.value;
    const transacted_on = body.querySelector(".edit-date").value;
    if (!(amount > 0)) {
      toast("金额须为大于 0 的数字", true);
      return;
    }
    if (!transacted_on) {
      toast("请选择交易日期", true);
      return;
    }
    const btn = body.querySelector(".btn-save");
    btn.disabled = true;
    try {
      await api(`/api/transactions/${tx.id}`, {
        method: "PATCH",
        body: JSON.stringify({ note, amount, type, transacted_on }),
      });
      toast("已保存");
      await refresh();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
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
    const db = body.querySelector(".btn-del");
    db.disabled = true;
    try {
      await api(`/api/transactions/${tx.id}`, { method: "DELETE" });
      toast("已删除");
      await refresh();
    } catch (err) {
      toast(err.message, true);
    } finally {
      db.disabled = false;
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
  const sub = $("#btn-login-submit");
  sub.disabled = true;
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
  } finally {
    sub.disabled = false;
  }
});

$("#btn-logout").addEventListener("click", async () => {
  beginBusy();
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    showLogin();
    state.keyword = "";
    const si = $("#input-tx-search");
    if (si) si.value = "";
    toast("已登出");
  } catch (err) {
    toast(err.message, true);
  } finally {
    endBusy();
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
  const ib = $("#btn-import");
  ib.disabled = true;
  beginBusy();
  try {
    const csrf = readCookie("ledger_csrf");
    const r = await fetch("/api/transactions/import", {
      method: "POST",
      body: fd,
      credentials: "include",
      headers: csrf ? { "X-CSRF-Token": csrf } : {},
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
  } catch (err) {
    toast(err.message, true);
    return;
  } finally {
    ib.disabled = false;
    endBusy();
  }
  await refresh();
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
  const ab = $("#btn-form-add-submit");
  ab.disabled = true;
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
  } finally {
    ab.disabled = false;
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

function openPasswordModal() {
  setAddSheetOpen(false);
  const m = $("#password-modal");
  const f = $("#form-password");
  if (f) f.reset();
  if (m) {
    m.classList.remove("hidden");
    m.setAttribute("aria-hidden", "false");
  }
}

function closePasswordModal() {
  const m = $("#password-modal");
  if (m) {
    m.classList.add("hidden");
    m.setAttribute("aria-hidden", "true");
  }
}

$("#btn-change-password")?.addEventListener("click", () => openPasswordModal());
$("#password-modal-backdrop")?.addEventListener("click", () =>
  closePasswordModal()
);
$("#password-modal-cancel")?.addEventListener("click", () =>
  closePasswordModal()
);

$("#form-password")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const sub = $("#btn-password-submit");
  sub.disabled = true;
  beginBusy();
  try {
    await api("/api/me/password", {
      method: "POST",
      body: JSON.stringify({
        old_password: fd.get("old_password"),
        new_password: fd.get("new_password"),
      }),
    });
    closePasswordModal();
    toast("密码已更新，请牢记新密码");
  } catch (err) {
    toast(err.message, true);
  } finally {
    sub.disabled = false;
    endBusy();
  }
});

$("#btn-export-csv")?.addEventListener("click", async () => {
  const qs = (() => {
    const p = new URLSearchParams();
    if (state.startDate && state.endDate) {
      p.set("start_date", state.startDate);
      p.set("end_date", state.endDate);
    }
    const kw = (state.keyword || "").trim();
    if (kw) p.set("keyword", kw);
    const s = p.toString();
    return s ? `?${s}` : "";
  })();
  beginBusy();
  try {
    const r = await fetch(`/api/transactions/export${qs}`, {
      credentials: "include",
    });
    if (!r.ok) {
      let msg = r.statusText;
      try {
        const j = await r.json();
        const d = j.detail;
        msg = Array.isArray(d)
          ? d.map((x) => x.msg || x).join("; ")
          : String(d || msg);
      } catch {
        msg = (await r.text()) || msg;
      }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ledger-export.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast("已开始下载");
  } catch (err) {
    toast(err.message || "导出失败", true);
  } finally {
    endBusy();
  }
});

$("#btn-load-more")?.addEventListener("click", async () => {
  if (state.txItems.length >= state.txTotal) return;
  const next = state.txPage + 1;
  const btn = $("#btn-load-more");
  btn.disabled = true;
  beginBusy();
  try {
    const txPayload = await api(`/api/transactions${buildTxQuery(next, 50)}`);
    state.txPage = next;
    state.txItems = state.txItems.concat(txPayload.items);
    renderGroupedList(state.txItems);
    updateLoadMoreUI();
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    endBusy();
  }
});

let _searchTimer = null;
$("#input-tx-search")?.addEventListener("input", (e) => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(async () => {
    state.keyword = e.target.value;
    await refresh();
  }, 320);
});
