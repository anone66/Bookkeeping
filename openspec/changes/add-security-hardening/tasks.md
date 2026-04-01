## 1. CSRF 防护

- [x] 1.1 选择 CSRF 方案（推荐 Double-Submit Cookie 或基于自定义请求头的模式，避免引入服务端状态）
- [x] 1.2 后端：为所有 POST/PATCH/DELETE 接口添加 CSRF 校验中间件
- [x] 1.3 前端：在 `api()` 请求封装中自动携带 CSRF Token
- [x] 1.4 编写测试：验证缺少 Token 时请求被拒绝

## 2. 登录速率限制

- [x] 2.1 实现基于 IP 的滑动窗口速率限制（如 5 次/分钟）
- [x] 2.2 连续失败达到阈值后返回 429 状态码
- [x] 2.3 编写测试：验证超限后请求被拒绝、冷却后恢复

## 3. 密码策略放宽

- [x] 3.1 更新 `PASSWORD_RE` 正则，允许常用特殊字符（`!@#$%^&*()-_+=~` 等）
- [x] 3.2 同步更新前端 HTML `pattern` 属性和提示文案
- [x] 3.3 编写测试：验证含特殊字符的密码可正常注册和登录

## 4. 会话清理

- [x] 4.1 在 `init_db()` 或 `lifespan` 中添加启动时清理过期 Session 的逻辑
- [x] 4.2 在 `get_current_user()` 中附加懒清理：每 N 次请求清理一批过期记录
- [x] 4.3 编写测试：验证过期 Session 被正确清理

## 5. Cookie Secure 标志

- [x] 5.1 通过请求的 `X-Forwarded-Proto` 或 `scheme` 判断是否为 HTTPS
- [x] 5.2 动态设置 `COOKIE_KWARGS["secure"]`
- [x] 5.3 确保开发环境（HTTP）不受影响

## 6. 安全响应头

- [x] 6.1 添加 FastAPI 中间件设置 `Content-Security-Policy`、`X-Content-Type-Options`、`X-Frame-Options` 等头
- [x] 6.2 验证头信息在响应中正确返回
