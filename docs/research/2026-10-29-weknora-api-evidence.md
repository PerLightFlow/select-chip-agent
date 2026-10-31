# WeKnora v0.9.0 API 接入证据

初次核查日期：2026-10-29（北京时间），当时仅分析官方 GitHub 发布元数据、路由、handler、service、repository 和类型定义。2026-10-30 已补充真实部署及合成文档 API 验收，见第 8 节；代码尚未提交 Git。本文回答现有 Django 企业知识模块可以调用哪些真实接口及其边界。

## 1. 固定版本

- 本次读取 GitHub `releases/latest` 返回 **v0.9.0**，发布时间 **2026-10-29 14:59:12**，tag 对应提交 **`f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7`**。此前“latest 还是 v0.8.3”的判断已经过时。[官方发布](https://github.com/Tencent/WeKnora/releases/tag/v0.9.0)、[tag API](https://api.github.com/repos/Tencent/WeKnora/git/ref/tags/v0.9.0)
- 同次读取的 main 为 `40192ace214ca046a86b590d69c1fe7286f3423e`，比 tag 多 2 个提交。本文引用全部固定到 v0.9.0 提交；本次比较中未发现本文使用的知识路由、知识检索请求、Wiki 页面及删除清理文件发生变化，不据此保证今后的 main。[比较](https://github.com/Tencent/WeKnora/compare/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7...40192ace214ca046a86b590d69c1fe7286f3423e)

## 2. 应采用的接口边界

现有 Agent 可继续负责交互与最终回答，只向 WeKnora 请求检索结果。**无需创建 WeKnora 聊天会话，也无需调用其 Agent 问答。** `POST /api/v1/knowledge-search` 明确只跑召回、重排序、合并、Top-K 阶段，没有 LLM 总结阶段。[handler](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/session/qa.go#L890-L1001)、[执行阶段](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/session_knowledge_qa.go#L965-L1023)

### 文档入库与管理

以下路径均带前缀 `/api/v1`。路由同时证明 scoped API Key 的读取/写入能力要求。[文档路由](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/router/routes_knowledge.go#L70-L185)

| 目的 | 方法与路径 | 已确认的请求/结果边界 |
|---|---|---|
| 上传文件 | POST `/knowledge-bases/{kb_id}/knowledge/file` | multipart 字段 `file`；支持 `fileName`、`metadata`（字符串值 JSON map）、`tag_ids`（逗号分隔）、`channel`、`process_config`。默认文件上限来自 `MAX_FILE_SIZE_MB`，默认 50 MB。 |
| 创建正文 | POST `/knowledge-bases/{kb_id}/knowledge/manual` | `title, content, status, tag_ids, channel, process_config`。`status=publish` 开始异步入库，省略为 `draft`。 |
| 获取处理状态 | GET `/knowledge/{id}` | 返回 `parse_status`、`summary_status`、`pending_subtasks_count`、`error_message`、最近活动等。 |
| 获取阶段详情 | GET `/knowledge/{id}/spans?attempt=N` | 阶段树及历史尝试；省略 attempt 为最近一次，Wiki 工作可表现为 `postprocess.wiki` 子阶段。 |
| 修改标题/摘要/元数据 | PUT `/knowledge/{id}` | 只接收 `title, description, custom_metadata`，未传字段保留。 |
| 修改手工正文 | PUT `/knowledge/manual/{id}` | 完整 Markdown 替换；仅手工文档，不能更新上传文件正文。 |
| 重解析 | POST `/knowledge/{id}/reparse` | 可覆盖 `process_config`；异步清理并重建解析产物/索引。 |
| 批量重解析 | POST `/knowledge/batch-reparse` | 路由存在，属 ingest 内容写操作；不是仅重试 Wiki 的专门接口。 |
| 删除 | DELETE `/knowledge/{id}` | 内容写操作；实际清理还涉及索引、文件与 Wiki。 |
| 原文/解析结果 | GET `/knowledge/{id}/preview`、GET `/knowledge/{id}/download`、GET `/chunks/{knowledge_id}` | 可用于业务后端转发来源预览；不要把服务 API Key 暴露给浏览器。 |

请求字段依据：[文件上传 handler](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L313-L445)、[手工正文类型](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/knowledge.go#L318-L340)、[状态类型](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/knowledge.go#L188-L250)、[阶段接口](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L680-L739)、[修改接口](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L2347-L2411)、[正文替换](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L2469-L2526)、[重解析](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L2531-L2553)。

**不要根据数据库的 `enable_status` 字段推断存在通用“禁用文件”API。** 当前公开 PUT 的请求类型没有此字段；上传文件也没有与手工 Markdown 相同的 `draft/publish` 创建参数。需要保留企业确认边界时，最稳妥的接法是确认后才同步正式知识库；确认前仍在本系统预览，或另建完全隔离的暂存 KB，并使用独立范围的 Key。[上传字段](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L313-L440)、[PUT 字段](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledge.go#L2347-L2355)

文件的 `metadata` 与 `custom_metadata` 不是同一个概念：后者是用户描述性元数据，前者还包含内部入库状态与 ID。自定义业务数据优先保留本地映射，向 WeKnora 写入时用明确的 `custom_metadata`，不把内部保留字段当扩展协议。[类型说明](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/knowledge.go#L224-L228)

### 原文检索

2026-10-30 真实 API 验收补充：v0.9.0 的 `AuthorizeTenantAPIKeyKnowledgeTargets` 在 Key 配置了 KB 白名单且请求包含任何 `knowledge_ids` 时直接返回 403，即使同时提供 KB ID 也不会放行。当前接入改用专用集成租户的 `retrieve` 只读 Key（不设 KB 白名单、无 full_access），写入 Key 仍按 KB 限定；应用继续传已发布文档 ID，不能通过添加整库 ID 绕过限制。[授权实现](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/tenant_api_key.go)

同次实测：注册密码要求 8–32 位且含字母和数字；API Key 创建响应的 `data.token` 为认证凭据，`data.api_key` 在启用存储加密时可能仍为加密值。已有 Key 从列表读取的值会解密，更新授权时保留该凭据，随后实际验证 Key 的访问权限。[创建响应](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/tenant.go#L688-L694)、[加密与读取 hook](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/tenant_api_key.go)

建议正式集成调用：

```http
POST /api/v1/knowledge-search
X-API-Key: <backend-only-key>
Content-Type: application/json

{
  "query": "图像采集模块由谁负责",
  "knowledge_ids": ["<current-published-document-id>"],
  "match_count": 8
}
```

- 支持 `query`、`knowledge_base_ids`、`knowledge_ids`、单 KB 的 `tag_ids` 或 scoped tag mentions，以及向量/关键词阈值、召回开关、`rerank` 覆盖。**没有任意 metadata 表达式，也没有 project_id 过滤字段。** 项目范围应先由 Django 解析为 KB/tag/当前文档 ID。[请求类型](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/session/types.go#L103-L121)
- **不能同时传完整 KB ID 和该 KB 的文档白名单来期待交集。** service 先建立整库目标；属于已整库搜索 KB 的显式文档会被跳过。因此严格按当前已发布版本过滤时，只传 `knowledge_ids`；多个 KB/文档组合须明确并集语义。[范围构造](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/session_knowledge_qa.go#L438-L554)
- 返回结构为 `{success, data, meta}`。片段含 `id`（chunk ID）、`knowledge_id`、`knowledge_base_id`、正文、标题、文件名、`source_locators`、检索分数等。需要保留原系统“版本+页码/行号”引用时，业务层将外部文档 ID 映射回自己的文档版本，位置优先用 source_locators；解析器未产出位置时不能编造页码。[结果类型](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/search.go#L162-L256)、[返回](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/session/qa.go#L991-L1000)
- `match_count` 的硬上限是 200。重排序可显式关闭；指定模型无法加载时会降级为召回顺序，并返回诊断，接入层应读取 `meta`，不要将“HTTP 200”当作完整重排已成功。[参数校验](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/session/qa.go#L1004-L1034)、[上限](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/retrieval_config.go#L46-L50)、[降级](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/session_knowledge_qa.go#L839-L872)
- 较底层的 `POST /knowledge-bases/{kb_id}/hybrid-search` 也返回片段，默认不重排，适合诊断召回。参数名是 `query_text`；与上面的 `query` 不同。合并 score 是排序用分数，不能直接解释为概率或“匹配百分比”。[handler](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/knowledgebase.go#L355-L458)、[底层参数](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/search.go#L260-L298)

## 3. Wiki 的可用 API 与实际可见性

| 目的 | 方法与路径（均以 /api/v1 开头） |
|---|---|
| 跨知识库 Wiki 搜索 | POST `/wiki-search` |
| 单知识库 Wiki 搜索 | GET `/knowledgebase/{kb_id}/wiki/search?q=...` |
| 页面列表 | GET `/knowledgebase/{kb_id}/wiki/pages` |
| 页面详情 | GET `/knowledgebase/{kb_id}/wiki/pages/{slug}` |
| 编辑/删除 | PUT / DELETE `/knowledgebase/{kb_id}/wiki/pages/{slug}` |
| 版本列表 | GET `/knowledgebase/{kb_id}/wiki/revisions/{slug}` |
| 回滚 | POST `/knowledgebase/{kb_id}/wiki/revert` |
| 检查/维护 | GET `.../lint`、POST `.../rebuild-links`、POST `.../auto-fix` |
| 总量与待办概况 | GET `.../stats` |

注意 Wiki 路径采用单数 `knowledgebase`，文档路径是 `knowledge-bases`，不能统一拼接猜测。[完整路由](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/router/routes_knowledge.go#L353-L398)

跨 KB Wiki 搜索请求只有 `query, knowledge_base_id, knowledge_base_ids, limit`，**不接受 knowledge_ids/tag/project 条件**。返回精简命中（KB、slug、标题、类型、摘要、匹配片段），没有完整的来源与状态；应随后读取页面详情，再执行本系统可见性和来源检查。[Wiki handler](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/wiki_page.go#L1121-L1215)

页面详情包含完整 Markdown、`status`、`source_refs`、`chunk_refs`、版本、最后编辑来源等。`source_refs` 可能为 `knowledgeID|title` 或旧格式的裸 ID；`chunk_refs` 提供片段 ID，摘要型页面可为空。引用应通过文档/片段映射取得，不能把 Wiki 摘要本身当作原始事实证明。[页面类型](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/wiki_page.go#L189-L285)

Wiki 修改支持版本乐观锁，但 **version=0 或未传时跳过检查**。接入现有编辑界面要显式传回读到的版本，处理 409，不进行盲覆盖。[请求定义](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/wiki_page.go#L382-L398)

### 三个需要业务层兜底的事实

1. **Wiki 发布不是人工审批。** 新建页面未指定状态时默认为 published；当前搜索 SQL 仅过滤 archived，因此 draft 同样可能出现在搜索结果中。不能复用 Wiki draft 来实现企业资料“未确认不可查”，也不能将 published 标记解释为负责人已确认。[默认值](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/wiki_page.go#L78-L90)、[搜索 SQL](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/repository/wiki_page.go#L1483-L1533)
2. **Wiki 搜索是页面文本检索，不是自动等价于原文向量检索。** PostgreSQL 路径用 POSIX 正则 `~*` 匹配 title/slug/summary/content，按字段优先级及更新时间排序，最多 50 条；SQLite 使用 LIKE。自然语言长问句的召回需要实测，通常由现有 Agent 提取项目名/实体/关键词搜索，再回原文核验。[实现](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/repository/wiki_page.go#L1474-L1536)
3. **一份 Wiki 页面可能综合多个项目/来源。** 在本系统支持“只查 A 项目”时，仅检查页面“存在 A 项目来源”不够，因为正文可能混入 B 项目内容。对于严格项目范围，优先使用分项目 KB 的 Wiki 或暂时只返回原文限定检索；跨项目 Wiki 只作为共享范围的派生知识。这是由页面多来源结构和 Wiki 搜索仅 KB 过滤推导的接入建议，尚未运行验证。[来源结构](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/wiki_page.go#L235-L247)、[搜索请求](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/handler/wiki_page.go#L1121-L1127)

## 4. 版本更新、撤回与删除不是单一 API 调用

- 当前源文件接口没有“上传新正文并保留业务版本历史”的统一协议；手工正文更新有内部 version 自增，但上传文件不可经此路径更新。建议保留 Django 文档与不可变版本记录，建立 `local_version_id → kb_id/knowledge_id` 映射，另记录同步任务状态，不用 Wiki 页版本替代文档版本。[手工更新](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/knowledge_create.go#L1032-L1139)
- reparse 只清理 Wiki 待办竞争，**不会同步撤回现有 Wiki 页面**；旧贡献的替换发生在后续异步 ingest。更新期间可能仍读到旧内容。[重解析 Wiki 处理](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/knowledge_delete.go#L365-L390)
- 源文档删除的 Wiki 清理明确采用 best-effort 和幂等策略：先写墓碑、清除 pending，再入队 retract；只有一个来源的页可以删除，多来源页会先删 source_refs/chunk_refs，正文修订依赖后续任务。错误可能只记日志。因此 DELETE 返回不等于所有派生文本同步撤回。[清理流程](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/knowledge_delete.go#L180-L319)
- **只在读时检查 source_refs 仍不够。** 多来源页可能已经删除某个 source_ref，但正文尚未完成异步修订。建议业务层先将文档版本标为不可检索，并将受影响 Wiki 页面或 KB 标为“待同步”；在撤回任务完成且内容核验前，停止向回答提供这部分 Wiki，仍可查未撤回的原文。该建议根据上述执行顺序推导。
- 回滚既要处理文件/原文索引，也要处理 Wiki 的生成结果。若首版需要严格“切换立即生效”，可通过隔离 KB/生成代次构建完成后切换指针实现；成本是额外存储和重新生成费用，必须试点测量。不要承诺现成 API 已提供跨 Django/WeKnora 的原子事务。

## 5. 入库完成与 Wiki 完成需要分开验收

`parse_status=finalizing` 表示原文已可检索而 enrichment 尚未结束；`completed` 表示子任务进入终态，不代表每个派生任务均成功。[状态注释](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/knowledge.go#L45-L62)

在 v0.9.0 固定源码里，Wiki 文件级失败超过 5 次后仍会归档到 SQL `task_dead_letters`、删除 pending 操作并释放该文档的 Wiki 子任务计数；计数归零可将文档晋级 completed 并清空 error_message。接入层必须单独保存/展示 `source_ready` 与 `wiki_ready/wiki_failed`，按最新 attempt 的 `postprocess.wiki` 详情核验，不能只读总状态。[重试归档](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/wiki_ingest.go#L1312-L1392)、[完成状态](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/repository/knowledge.go#L661-L747)、[Wiki 子阶段](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/application/service/wiki_ingest.go#L469-L490)

启动恢复扫描 `task_pending_ops`；Redis/asynq 的运行时“立即执行”操纵的是它自己的排队/归档任务，两者不等同于 SQL Wiki 死信恢复。当前公开 Wiki 路由中未见专项“按文档批量重试 SQL Wiki 死信”接口；可用 reparse 间接重触发，但会重做解析/索引。需要把专项恢复作为试点验收项或后续上游小补丁，而非在业务服务直接写 WeKnora 表。[启动恢复](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/container/recover_pending_wiki_tasks.go#L69-L105)、[运行时重放](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/router/task_inspector.go#L729-L743)、[Wiki 路由](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/router/routes_knowledge.go#L353-L398)

公开 issue #4816 当前仍 open，报告基于 v0.8.3 的同类问题。该报告不是本次复现结果；上面的 v0.9.0 结论独立来自固定源码。[问题记录](https://github.com/Tencent/WeKnora/issues/4816)

## 6. 服务账号与能力范围

API Key 可用 `X-API-Key` 传递。Key 具备 tenant 范围、capabilities、KB 白名单、到期与撤销字段。建议 Django 内部至少拆分只读 retrieval key 和同步 worker 的 ingest+retrieve key，配置到批准的 KB；生命周期初始化另用具备 manage_kbs 的受控运维凭据。[认证读取](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/middleware/auth.go#L171-L178)、[Key 类型与能力](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/tenant_api_key.go#L15-L105)

- `retrieve`：文档、片段和 Wiki 的读/搜；
- `ingest`：允许内容上传、修改、删除，仍受 KB 白名单限制；**不是只允许新增**；
- `manage_kbs`：建库、配置、复制、删除知识库；
- 不需要给当前问答路径 `chat, message_history, manage_agents, manage_models` 或 full_access。

权限基于路由能力与 KB 范围，并不自动理解 Django 的提交者、项目、确认状态和本地历史版本，因此本系统业务鉴权必须先执行。[Key 能力](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/types/tenant_api_key.go#L71-L123)、[网关](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/middleware/api_key_gate.go#L108-L128)、[文档路由授权](https://github.com/Tencent/WeKnora/blob/f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7/internal/router/routes_knowledge.go#L125-L185)

## 7. 需要通过试点回答的未知项

1. Kimi 当前端点/模型执行 Wiki 结构化提取、合并、重试的兼容性与成本；本次只核对接口，未跑模型。
2. 中文项目名、人员缩写、芯片型号的向量/关键词/重排/Wiki 联合召回质量；返回空结果是否来自未入库、过滤或阈值。
3. 删除/更新后旧事实在原文结果、Wiki 页面、正文引用及缓存中的实际残留时间；必须包括模型不可用和重复删除场景。
4. Wiki SQL 死信的批量发现、仅 Wiki 恢复机制，以及失败后 `completed` 与真实 Wiki 状态的产品展示。
5. 一万份资料时文档 ID 白名单规模、API 体积、批量轮询吞吐及 KB 划分策略；不能据接口类型推断容量。
6. PDF/Office 解析器实际提供的位置精度，以及现有来源链接能否一一映射；缺页码时须降级为明确的文档/片段引用。
7. 对 `knowledge_ids`、最新版本过滤和 Wiki 页面状态进行真实集成反例测试，尤其不能误传整库 ID 扩大范围。

实现优先级建议：先做好“确认发布 → 幂等同步 → 原文检索 → 本地引用”，再接“Wiki 搜索 → 页面读取 → 来源/同步代次检查”。Wiki 不作为负责人、芯片版本等已确认项目记录的唯一真相源。

## 8. 2026-10-30 真实服务验收补充

独立租户的合成资料已通过上传、原文索引、严格文档范围、向量检索、关键词检索、原文读取和删除。隔离 Django 数据库进一步通过草稿不上传、确认后的 outbox 同步、元数据标记、版本引用及撤回后立即排除旧资料。正式资料未被测试修改；Wiki 和真实项目语料仍待验收。

DELETE 返回成功仅代表异步任务已受理，不能立即标记远端已删除。本地记录 `delete_requested_at`，继续查询至 GET 返回 404；等待期间不重复提交已受理的 DELETE。真实探针和业务验收均验证了最终删除。

ParadeDB v0.25.11 实测中，KB 关闭问题生成所附加的过滤 SQL 会使关键词通道报 `Unsupported query shape`；混合请求仍可能凭向量结果返回 HTTP 200。当前专用租户采用 KB 开启问题生成标志、每次应用上传明确关闭问题生成/摘要/图谱/多模态的兼容配置，且没有配置聊天模型；两个检索通道分别验收成功。此方案不适用于绕过应用的直接上传。具体约束及后续启用 Wiki 前的复核要求见 [运行说明](../../deploy/weknora/README.md)。数据库诊断中的索引与会话配置试验均已回滚，没有保留数据库补丁。

完整上线结果、镜像标识、测试范围和待办见 [v0.3.0 发布记录](../deployment/2026-10-30-weknora-v030.md)。
