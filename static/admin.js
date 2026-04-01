let adminSelfId = null;

function showAdmin(me) {
  $("#view-login").classList.add("hidden");
  $("#view-admin").classList.remove("hidden");
  $("#whoami").textContent = `${me.username}（管理员）`;
  adminSelfId = me.id;
}

function showLogin() {
  $("#view-admin").classList.add("hidden");
  $("#view-login").classList.remove("hidden");
}

async function loadUsers() {
  beginBusy();
  try {
    const users = await api("/api/admin/users");
    const tb = $("#user-tbody");
    tb.innerHTML = "";
    for (const u of users) {
      const tr = document.createElement("tr");
      const statusText = u.is_active ? "正常" : "已禁用";
      tr.innerHTML = `
      <td>${u.id}</td>
      <td>${escapeHtml(u.username)}</td>
      <td>${u.role === "admin" ? "管理员" : "用户"}</td>
      <td>${statusText}</td>
      <td class="admin-row-actions"></td>
    `;
      const actions = tr.querySelector(".admin-row-actions");
      if (u.is_active) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-danger";
        b.textContent = "禁用";
        b.addEventListener("click", async () => {
          const ok = await window.confirmDialog({
            title: "禁用用户",
            message: `确定禁用用户「${u.username}」？该用户将无法再登录。`,
            confirmText: "禁用",
            cancelText: "取消",
            danger: true,
          });
          if (!ok) return;
          try {
            await api(`/api/admin/users/${u.id}`, {
              method: "PATCH",
              body: JSON.stringify({ is_active: false }),
            });
            toast("已禁用");
            await loadUsers();
          } catch (e) {
            toast(e.message, true);
          }
        });
        actions.appendChild(b);
      } else {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-primary";
        b.textContent = "启用";
        b.addEventListener("click", async () => {
          try {
            await api(`/api/admin/users/${u.id}`, {
              method: "PATCH",
              body: JSON.stringify({ is_active: true }),
            });
            toast("已启用");
            await loadUsers();
          } catch (e) {
            toast(e.message, true);
          }
        });
        actions.appendChild(b);
      }
      const inpWrap = document.createElement("div");
      inpWrap.className = "input-wrap";
      inpWrap.style.position = "relative";
      inpWrap.style.display = "inline-block";

      const inp = document.createElement("input");
      inp.type = "password";
      inp.placeholder = "新密码";
      inp.autocomplete = "new-password";
      inp.className = "pwd-input";

      const eyeBtn = document.createElement("button");
      eyeBtn.type = "button";
      eyeBtn.className = "btn-eye material-symbols-outlined";
      eyeBtn.textContent = "visibility_off";
      eyeBtn.title = "显示/隐藏密码";

      inpWrap.appendChild(inp);
      inpWrap.appendChild(eyeBtn);

      const bp = document.createElement("button");
      bp.type = "button";
      bp.className = "btn btn-ghost";
      bp.textContent = "重置密码";
      bp.addEventListener("click", async () => {
        const pw = inp.value.trim();
        if (pw.length < 6) {
          toast(
            "新密码至少 6 位，支持字母、数字、@ . 及 ! # $ % ^ & * ( ) - _ + = ~ 等符号",
            true
          );
          return;
        }
        try {
          await api(`/api/admin/users/${u.id}`, {
            method: "PATCH",
            body: JSON.stringify({ password: pw }),
          });
          inp.value = "";
          toast("密码已更新");
        } catch (e) {
          toast(e.message, true);
        }
      });
      actions.appendChild(inpWrap);
      actions.appendChild(bp);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-danger btn-loading";
      del.textContent = "删除";
      del.style.marginLeft = "0.35rem";
      if (u.id === adminSelfId) {
        del.disabled = true;
        del.title = "不能删除当前登录账号";
      } else {
        del.addEventListener("click", async () => {
          const ok = await window.confirmDialog({
            title: "删除用户",
            message: `确定永久删除用户「${u.username}」及其全部流水与登录会话？此操作不可恢复。`,
            confirmText: "删除",
            cancelText: "取消",
            danger: true,
          });
          if (!ok) return;
          del.disabled = true;
          beginBusy();
          try {
            await api(`/api/admin/users/${u.id}`, {
              method: "DELETE",
              body: "{}",
            });
            toast("已删除用户");
          } catch (e) {
            toast(e.message, true);
            return;
          } finally {
            del.disabled = false;
            endBusy();
          }
          await loadUsers();
        });
      }
      actions.appendChild(del);
      tb.appendChild(tr);
    }
  } finally {
    endBusy();
  }
}

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const sub = $("#admin-btn-login-submit");
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
    if (me.role !== "admin") {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
      throw new Error("需要管理员账号");
    }
    showAdmin(me);
    await loadUsers();
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
  } catch (e) {
    toast(e.message, true);
  } finally {
    endBusy();
  }
});

$("#form-create").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const sub = $("#admin-btn-create-submit");
  sub.disabled = true;
  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username: fd.get("username"),
        password: fd.get("password"),
        role: fd.get("role"),
      }),
    });
    e.target.reset();
    toast("用户已创建");
    await loadUsers();
  } catch (err) {
    toast(err.message, true);
  } finally {
    sub.disabled = false;
  }
});

(async function boot() {
  try {
    const me = await api("/api/me");
    if (me.role !== "admin") {
      showLogin();
      toast("请使用管理员账号登录", true);
      return;
    }
    showAdmin(me);
    await loadUsers();
  } catch {
    showLogin();
  }
})();
