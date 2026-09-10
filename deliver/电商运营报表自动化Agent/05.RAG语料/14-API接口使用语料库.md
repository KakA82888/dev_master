# API接口使用语料库

**主题：** 后端 RESTful API 的列表、请求响应与调用示例
**适用范围：** 前端开发、联调人员、学习者
**版本：** v1.0

---

## Q: 系统提供哪些 API 接口？

**A:** 分为三组：

| 分组 | 接口 | 说明 |
|---|---|---|
| 健康检查 | `GET /api/health` | 服务存活探测 |
| 鉴权 | `POST /api/auth/register` | 注册 |
| 鉴权 | `POST /api/auth/login` | 登录，返回 JWT |
| 报告 | `POST /api/reports/generate` | 生成报告（支持异步） |
| 报告 | `GET /api/reports` | 报告列表 |
| 报告 | `GET /api/reports/{id}` | 报告详情 |
| 报告 | `POST /api/reports/{id}/confirm` | 确认报告 |
| 报告 | `POST /api/reports/{id}/archive` | 归档报告 |
| 报告 | `DELETE /api/reports/{id}` | 删除报告 |
| 报告 | `GET /api/reports/{id}/export?fmt=docx\|markdown` | 导出 |

启动服务后访问 `/docs` 可查看自动生成的交互式接口文档。

**标签：** API列表, 接口清单, RESTful, 接口使用

---

## Q: 如何调用鉴权接口？

**A:**

```bash
# 注册
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice1234"}'

# 登录（返回 access_token）
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo1234"}'
```

后续请求需在请求头携带：`Authorization: Bearer <access_token>`。

**标签：** 鉴权接口, 注册, 登录, 调用示例

---

## Q: 生成报告接口怎么调用？

**A:**

```bash
curl -X POST http://127.0.0.1:8000/api/reports/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"instruction":"生成上月德国月报"}'
```

响应包含报告 id 与初始状态。异步模式下应立即返回（状态 pending），随后前端轮询 `GET /api/reports/{id}` 获取进度。

**标签：** 生成接口, 异步, 请求示例, 接口使用

---

## Q: 报告详情接口返回什么结构？

**A:** 主要字段：

| 字段 | 说明 |
|---|---|
| id | 报告 ID |
| instruction | 用户原始指令 |
| status | 状态（pending/running/drafted/confirmed/archived/failed） |
| report_type / start / end / country | 解析出的意图 |
| markdown | 报告正文（Markdown） |
| metrics_json | 指标数据（JSON） |
| version | 版本号（每次确认 +1） |
| created_at / updated_at | 时间戳 |

**标签：** 详情接口, 响应结构, 字段说明, 接口使用

---

## Q: 确认与归档接口如何使用？有什么约束？

**A:**

```bash
# 确认（仅 drafted 状态可用）
curl -X POST http://127.0.0.1:8000/api/reports/1/confirm \
  -H "Authorization: Bearer <token>"

# 归档（仅 confirmed 状态可用）
curl -X POST http://127.0.0.1:8000/api/reports/1/archive \
  -H "Authorization: Bearer <token>"
```

状态不符时返回 400 并给出原因（如"重复确认"）。确认会把版本号 +1。

**标签：** 确认接口, 归档接口, 状态守卫, 接口使用

---

## Q: 导出接口如何调用？

**A:**

```bash
curl -OJ "http://127.0.0.1:8000/api/reports/1/export?fmt=markdown" \
  -H "Authorization: Bearer <token>"

curl -OJ "http://127.0.0.1:8000/api/reports/1/export?fmt=docx" \
  -H "Authorization: Bearer <token>"
```

- `fmt=markdown`：返回 `.md`
- `fmt=docx`：返回 `.docx`（Word）

响应头 `Content-Disposition` 携带文件名（支持中文）。未完成状态（pending/running/failed）会拒绝导出。

**标签：** 导出接口, 文件下载, 中文文件名, 接口使用

---

## Q: 接口的鉴权与错误码约定是什么？

**A:**

| 状态码 | 含义 | 场景 |
|---|---|---|
| 200 | 成功 | 正常响应 |
| 400 | 请求错误 | 参数非法、状态不符、重复注册 |
| 401 | 未授权 | 缺少或无效 JWT |
| 404 | 未找到 | 报告不存在**或属于其他用户**（不泄露存在性） |
| 500 | 服务异常 | 未预期的内部错误 |

所有需鉴权的接口都要求 `Authorization: Bearer <token>`。

**标签：** 错误码, 鉴权约定, HTTP状态码, 接口使用

---

## Q: 前端如何封装接口调用？

**A:** 统一在 `api.ts` 中封装：
1. 自动附加 `Authorization` 头（从本地存储读取 token）
2. 统一处理错误（解析后端返回的错误信息，抛出具语义的 `ApiError`）
3. 提供业务方法（登录/生成/轮询详情/列表/确认/归档/删除/导出）
4. 导出方法解析响应头文件名并触发浏览器下载

集中封装的好处是：token 管理、错误处理、下载逻辑只写一次。

**标签：** 接口封装, api.ts, 前端调用, 接口使用
