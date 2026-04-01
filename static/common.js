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

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
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

function toast(msg, err = false) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.className = `toast${err ? " err" : ""}`;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2800);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.body.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-eye");
  if (btn) {
    const wrap = btn.closest(".input-wrap");
    if (wrap) {
      const inp = wrap.querySelector(".pwd-input");
      if (inp) {
        if (inp.type === "password") {
          inp.type = "text";
          btn.textContent = "visibility";
        } else {
          inp.type = "password";
          btn.textContent = "visibility_off";
        }
      }
    }
  }
});
