## 上下文

- 栈：FastAPI + SQLite + 服务端渲染/模板记账页；交易表已有 `user_id`、`type`（expense/income）、`amount_cents`、`note`、`transacted_on` 等。
- 样例文件位于仓库 `账单/`：支付宝为 UTF-8（或带 BOM）CSV，前有若干说明行，明细表头在第 25 行附近（以「交易时间」起始）；微信为 XLSX，明细表头在第 18 行（`A18` 起），数据从第 19 行起，`交易时间` 列为 Excel 日期序列（非 ISO 字符串）。

## 目标 / 非目标

- 目标：最小可用导入；平台与文件类型校验；仅成功状态行；跳过不计收支/中性；按外部单号去重；导入结果对当前用户列表与汇总可见。
- 非目标：自动处理银行卡重复记账提示、多币种、退款合并、OCR、非官方改版格式的长期兼容承诺。

## 决策

1. **上传方式**：通过记账页表单 `multipart/form-data` 上传文件至受会话保护的导入端点，避免客户端直写数据库。
2. **支付宝行级映射**：`收/支` 为「支出」→ expense、「收入」→ income；「不计收支」整行跳过；`金额` 转为分（`amount_cents`）；`交易时间` 解析为日期。除金额、类型、日期外，导出中的下列内容**必须写入专门列**（手工录入交易这些列为 `NULL`）：
   - **交易分类** → `bill_category`
   - **交易对方** → `bill_counterparty`
   - **商品说明** → `bill_product`
   - **收/付款方式** → `bill_payment_method`
   - **商家订单号** → `bill_merchant_no`（与用作幂等的「交易订单号」区分）
   - **备注**（导出文件列）→ `bill_export_note`（可与用户 `note` 并存；用户后续可继续编辑 `note`，不得无故清空 `bill_export_note`）
3. **微信行级映射**：`收/支`、`金额`、`交易时间`、状态过滤、跳过中性同前。列对齐写入：
   - **交易类型** → `bill_category`
   - **交易对方** → `bill_counterparty`
   - **商品** → `bill_product`
   - **支付方式** → `bill_payment_method`
   - **商户单号** → `bill_merchant_no`
   - **备注** → `bill_export_note`
4. **幂等**：在 `transactions` 表增加可空字段 `import_platform`（`alipay` / `wechat`，手工为 `NULL`）、`external_id`（支付宝「交易订单号」/ 微信「交易单号」），并建立 `(user_id, import_platform, external_id)` 唯一索引（仅当 `import_platform` 与 `external_id` 均非空时参与唯一性；SQLite 可用部分索引或应用层保证）；冲突则跳过重复插入。
5. **依赖**：新增轻量 XLSX 读取库（如 `openpyxl`）仅用于服务端解析，不把大文件完全载入内存的策略在实现时按需流式/分批（若行数可接受则简单实现即可）。

## 风险 / 权衡

- 导出格式变更会导致解析失败 → 返回可读错误信息；单元测试固定样例行以防回归。
- Excel 日期与服务器时区 → 规范约定以导出说明中的时区（样例为 UTC+8）转换落到 `transacted_on` 日历日。

## 迁移计划

- 启动迁移添加可空列：`import_platform`、`external_id`、`bill_category`、`bill_counterparty`、`bill_product`、`bill_payment_method`、`bill_merchant_no`、`bill_export_note` 及唯一索引；既有手工数据上述列均为 `NULL`。

## 待决问题

- 无（首期以仓库内两份样例为解析契约；若后续用户导出列顺序变化，再通过新变更扩展）。
