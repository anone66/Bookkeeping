# 个人收支记账（本地 Web · 多用户）

浏览器登录后记录本人消费/收入；数据在 **SQLite**（`data/ledger.db`）。**管理员**可通过 `/admin` 维护用户（创建、禁用/启用、重置密码）。

## 环境

- Python 3.11+

## 首次启动（首轮管理员）

数据库中没有任何用户时，进程会**拒绝启动**，除非设置：

| 变量 | 说明 |
|------|------|
| `LEDGER_BOOTSTRAP_ADMIN_USER` | 管理员登录名（3–64 位，仅字母、数字、`@`、`.`，存库为小写） |
| `LEDGER_BOOTSTRAP_ADMIN_PASSWORD` | 管理员密码（≥6 位，同上字符集） |

示例：

```bash
export LEDGER_BOOTSTRAP_ADMIN_USER='myadmin'
export LEDGER_BOOTSTRAP_ADMIN_PASSWORD='yourSecret1'
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

之后可用该账号登录，再在管理端创建其他用户。

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 记账首页：<http://127.0.0.1:8000/>
- 管理端：<http://127.0.0.1:8000/admin>

## 时间维度记账与统计

- 新增交易时可选择`交易日期`，默认当天（按 UTC 日期）。
- 交易列表支持按`年份/月份`筛选，并按年月分组展示。
- 页面同时显示：
  - 筛选范围汇总（当前年份月份条件）
  - 总体汇总（所有时间）
- 统计口径以`交易日期`为准，不以创建时间为准。

## 从旧版单用户库升级

若已有不含 `user_id` 的旧表 `transactions`，启动迁移会为所有旧记录打上**当前第一个用户**（通常为首轮管理员）的 `user_id`。建议升级前备份 `data/ledger.db`。

## 数据与会话

- 请单进程访问同一库文件；会话 Cookie 名 `ledger_session`（`HttpOnly`、`SameSite=Lax`）。
- 生产环境建议 HTTPS，并为 Cookie 配置 `Secure`（可按部署在代码中开启）。

## 测试

```bash
pip install pytest
pytest tests/ -q
```
