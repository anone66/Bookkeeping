# 变更：修复已知缺陷与提升代码质量

## 为什么

代码审查发现后端存在冗余 SQL 查询（`api_summary` 中对同一无筛选聚合执行两次）、前端存在 `parseFloat` 误传 radix、缺失 `favicon.png` 引发 404、`.gitignore` 不完整导致敏感文件可能被提交、多个模态框的 `aria-hidden` 属性未正确切换影响无障碍、`app.js` 与 `admin.js` 之间大量逻辑重复增加维护成本等一系列影响正确性与可维护性的问题。这些问题单独看不严重，但累积起来拖慢开发效率且降低产品质量。

## 变更内容

### 后端
- 移除 `api_summary` 中重复的无筛选聚合查询（当前执行两次相同 SQL）
- 将 `bill_import.py` 中循环内定义的 `g()` 闭包移到循环体外，避免每次迭代重建函数对象
- 将 `pytest` 加入 `requirements.txt`（或新增 `requirements-dev.txt`）

### 前端
- 提供 `favicon.png`，消除 404
- 修正 `parseFloat(value, 10)` 中多余的 radix 参数
- 为 `import-modal` 和 `source-modal` 正确切换 `aria-hidden` 属性
- 将 `app.js` 与 `admin.js` 的重复逻辑（`initTheme`、`api`、`toast`、`escapeHtml`、密码显隐切换）提取为公共模块 `common.js`

### 工程
- 补全 `.gitignore`（`.venv/`、`__pycache__/`、`data/`、`.env`、`*.pyc`、`*.db`）
- 新增 `.gitattributes` 统一行尾符，消除 CRLF 警告

## 影响

- 受影响规范：`personal-ledger`、`ui-theme`
- 受影响代码：`app/main.py`、`app/bill_import.py`、`static/app.js`、`static/admin.js`、`static/index.html`、`static/admin.html`、`.gitignore`
