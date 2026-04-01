## 1. 后端缺陷修复

- [x] 1.1 移除 `app/main.py` 中 `api_summary` 的冗余无筛选聚合查询（第 629-638 行），保留 `overall` 即可
- [x] 1.2 将 `app/bill_import.py` 中 `parse_alipay_csv` 和 `parse_wechat_xlsx` 循环体内的 `g()` 函数提取到循环外部
- [x] 1.3 将 `pytest` 加入 `requirements.txt` 或新增 `requirements-dev.txt`

## 2. 前端缺陷修复

- [x] 2.1 提供 `static/favicon.png`，确保 HTML 引用不再 404
- [x] 2.2 修正 `static/app.js` 中 `parseFloat(value, 10)` 为 `parseFloat(value)`
- [x] 2.3 在 `import-modal` 和 `source-modal` 的打开/关闭逻辑中正确切换 `aria-hidden` 属性

## 3. 前端代码去重

- [x] 3.1 提取 `app.js` 与 `admin.js` 的公共逻辑为 `static/common.js`（含 `initTheme`、主题切换、`api`、`toast`、`escapeHtml`、密码显隐切换）
- [x] 3.2 在 `index.html` 和 `admin.html` 中引入 `common.js`，删除两处重复代码
- [x] 3.3 确保重构后所有原有功能正常，通过手工验证或已有测试

## 4. 工程规范

- [x] 4.1 补全 `.gitignore`：添加 `.venv/`、`__pycache__/`、`*.pyc`、`data/`、`*.db`、`.env`
- [x] 4.2 新增 `.gitattributes` 文件，设置 `* text=auto` 统一行尾
- [x] 4.3 提交当前已有的两个未提交修复（`app.js` 本月筛选日期、`style.css` 移动端 z-index）
