/** 记账页与管理端共用：主题、API、提示、转义、密码显隐 */

const $ = (sel, el = document) => el.querySelector(sel);

/** 默认浅色（参考 Amethyst）；深色为 data-theme="dark" */
function initTheme() {
  const saved = localStorage.getItem("theme");
  const btn = $("#btn-theme");
  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    if (btn) btn.textContent = "☀️";
  } else {
    document.documentElement.removeAttribute("data-theme");
    if (btn) btn.textContent = "🌙";
  }
}
initTheme();

const themeBtn = $("#btn-theme");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const isDark =
      document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("theme", "light");
      themeBtn.textContent = "🌙";
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
      themeBtn.textContent = "☀️";
    }
  });
}

function readCookie(name) {
  const parts = String(document.cookie || "").split(";").map((s) => s.trim());
  for (const p of parts) {
    if (p.startsWith(`${name}=`)) return decodeURIComponent(p.slice(name.length + 1));
  }
  return "";
}

async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const hdrs = { "Content-Type": "application/json", ...opts.headers };
  if (method === "POST" || method === "PATCH" || method === "DELETE") {
    const tok = readCookie("ledger_csrf");
    if (tok) hdrs["X-CSRF-Token"] = tok;
  }
  const r = await fetch(path, {
    headers: hdrs,
    credentials: "include",
    ...opts,
  });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text || r.statusText };
  }
  if (!r.ok) {
    const msg =
      (data && data.detail) ||
      (typeof data === "object" && JSON.stringify(data)) ||
      r.statusText;
    throw new Error(
      Array.isArray(msg) ? msg.map((m) => m.msg || m).join("; ") : String(msg)
    );
  }
  return data;
}

let _busyDepth = 0;

function beginBusy() {
  _busyDepth++;
  const bar = $("#top-progress");
  if (bar) {
    bar.classList.remove("hidden");
    bar.setAttribute("aria-hidden", "false");
  }
  document.body.classList.add("global-busy");
}

function endBusy() {
  _busyDepth = Math.max(0, _busyDepth - 1);
  if (_busyDepth === 0) {
    const bar = $("#top-progress");
    if (bar) {
      bar.classList.add("hidden");
      bar.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("global-busy");
  }
}

function dismissToast() {
  const el = $("#toast");
  if (!el) return;
  clearTimeout(toast._t);
  toast._t = null;
  el.classList.add("hidden");
}

function toast(msg, err = false) {
  const el = $("#toast");
  const textEl = $("#toast-text");
  if (!el) return;
  if (textEl) textEl.textContent = msg;
  else el.textContent = msg;
  el.className = `toast${err ? " err" : ""}`;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(dismissToast, 2800);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.body.addEventListener("click", (e) => {
  const eye = e.target.closest(".btn-eye");
  if (eye) {
    const wrap = eye.closest(".input-wrap");
    if (wrap) {
      const inp = wrap.querySelector(".pwd-input");
      if (inp) {
        if (inp.type === "password") {
          inp.type = "text";
          eye.textContent = "visibility";
        } else {
          inp.type = "password";
          eye.textContent = "visibility_off";
        }
      }
    }
  }
  const tclose = e.target.closest(".toast-close");
  if (tclose) {
    dismissToast();
    return;
  }
  if (e.target.closest("#toast") && !$("#toast")?.classList.contains("hidden")) {
    dismissToast();
  }
});
