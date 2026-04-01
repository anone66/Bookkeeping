/**
 * 与主题一致的确认弹窗。依赖页面中存在 #confirm-modal 节点。
 */
(function () {
  function $(sel) {
    return document.querySelector(sel);
  }

  /**
   * @param {{ title: string; message: string; confirmText?: string; cancelText?: string; danger?: boolean }} options
   * @returns {Promise<boolean>}
   */
  function confirmDialog(options) {
    var title = options.title || "确认";
    var message = options.message || "";
    var confirmText = options.confirmText || "确定";
    var cancelText = options.cancelText || "取消";
    var danger = !!options.danger;

    var overlay = $("#confirm-modal");
    var titleEl = $("#confirm-modal-title");
    var msgEl = $("#confirm-modal-message");
    var okBtn = $("#confirm-modal-ok");
    var cancelBtn = $("#confirm-modal-cancel");
    var backdrop = $("#confirm-modal-backdrop");

    if (
      !overlay ||
      !titleEl ||
      !msgEl ||
      !okBtn ||
      !cancelBtn ||
      !backdrop
    ) {
      return Promise.resolve(
        window.confirm(message || title)
      );
    }

    titleEl.textContent = title;
    msgEl.textContent = message;
    okBtn.textContent = confirmText;
    cancelBtn.textContent = cancelText;

    okBtn.className = danger ? "btn btn-danger" : "btn btn-primary";
    cancelBtn.className = "btn btn-ghost";

    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");

    return new Promise(function (resolve) {
      var settled = false;

      function finish(val) {
        if (settled) return;
        settled = true;
        overlay.classList.add("hidden");
        overlay.setAttribute("aria-hidden", "true");
        document.removeEventListener("keydown", onKey);
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        backdrop.removeEventListener("click", onCancel);
        resolve(val);
      }

      function onOk() {
        finish(true);
      }

      function onCancel() {
        finish(false);
      }

      function onKey(e) {
        if (e.key === "Escape") onCancel();
      }

      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
      backdrop.addEventListener("click", onCancel);
      document.addEventListener("keydown", onKey);

      cancelBtn.focus();
    });
  }

  window.confirmDialog = confirmDialog;
})();
