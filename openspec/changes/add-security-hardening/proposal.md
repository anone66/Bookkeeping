# 变更：安全加固与会话管理优化

## 为什么

当前系统存在多项安全薄弱环节：使用 Cookie 会话认证但未实施 CSRF 防护，状态变更接口易受跨站请求伪造攻击；登录端点无速率限制，可被暴力破解；密码字符集仅允许 `[a-zA-Z0-9@.]`，排除了常用特殊字符，降低了密码强度上限；Session 过期后不清理导致表无限膨胀；Cookie 在 HTTPS 环境下未自动设置 `Secure` 标志；应用未返回 `Content-Security-Policy` 等安全响应头。这些问题在互联网部署场景下构成实际风险。

## 变更内容

- 为所有状态变更接口（POST/PATCH/DELETE）引入 CSRF Token 校验机制
- 在 `/api/auth/login` 端点增加速率限制（基于 IP 或用户名的短时间窗口限制）
- 放宽密码字符集，允许常用特殊字符（`!@#$%^&*()-_+=`等），同时保持最短 6 位要求
- 实现过期 Session 的定期或懒清理策略
- 当检测到 HTTPS 部署时，自动为会话 Cookie 设置 `Secure` 标志
- 添加 `Content-Security-Policy` 等安全响应头

## 影响

- 受影响规范：`user-auth`
- 受影响代码：`app/main.py`、`static/app.js`、`static/admin.js`（CSRF Token 注入）
- **重大变更**：放宽密码字符集后，旧版客户端的前端正则校验需同步更新
