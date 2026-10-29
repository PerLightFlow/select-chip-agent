# 企业研发助手 · v0.2

通过连续对话梳理产品需求、联网调研芯片，并查询和维护企业项目知识。保留原有账号和管理员体系。

## 使用流程

1. 在登录页选择“没有账号？创建账号”，填写用户名、密码和确认密码，注册后自动登录；已有账号可直接登录。登录后直接描述产品想法。助手每轮追问关键缺口，保存本会话需求摘要，并自主安排搜索；可以随时纠正条件、停止或继续。
2. 调研结果通常比较 3–5 个候选，说明接口与参数、适配条件、风险和来源。来源不足时明确未知。候选不依赖预先建立的芯片目录。
3. 在“企业知识”上传文字 PDF、DOCX、XLSX/CSV、Markdown/TXT，或直接粘贴文字；解析后先查看预览，再确认共享。新版本、撤回及原件下载均保留入口。
4. 在“项目卡片”维护项目代号、别名、模块、芯片、负责人/参与人、依据与生效日期；也可以在对话中要求整理。助手提出的变更需要在页面确认，才会进入共享知识。
5. 最近对话右侧可删除对话，确认后生效；正在调研时需先停止。回答完成后调研进度自动隐藏。
6. 所有登录用户共享已确认知识；个人聊天、需求摘要和临时调研结果私有。普通用户维护自己的贡献，跨用户修改交管理员确认，版本冲突不覆盖。

模型漏保存需求摘要时，应用会在私有摘要中保留用户本轮原话，明确标注提问不等于已确认事实。原话补充有上下文长度上限，完整聊天记录保持；正常调用摘要工具后使用其整理结果。

知识库目前采用项目结构化查询与中文关键词全文检索，包含来源和版本，不宣称已实现语义向量检索。旧版个人选型记录与规则 API 继续保留，旧入口说明见 [v0.1 文档](docs/v01-readme.md)。

## 源码与版本管理

源码统一维护于 [PerLightFlow/select-chip-agent](https://github.com/PerLightFlow/select-chip-agent)，默认分支为 `main`。仓库根目录包含 `backend/`、`frontend/`、`deploy/` 和 `docs/`；需求、设计决策与术语也随代码保存。数据库、上传资料、模型密钥、镜像包、验收运行产物和日志不进入 Git。

当前已部署组合为网页 `chat-controls-v027`、HTTP 后端 `signup-v026`、后台任务 `reframing-v02.5`；健康 API 版本仍为 `0.2.6`。部署记录见 [运行说明](docs/operations-v02.md)，需求见 [已确认需求](docs/requirements/2026-10-29-agent-reframing.md)。

## Docker 启动

```bash
cp .env.example .env
# 填写随机 DJANGO_SECRET_KEY、POSTGRES_PASSWORD、SEARXNG_SECRET，以及模型配置
# .env 只保存在服务器，chmod 600 .env
docker compose up --build -d
docker compose exec backend python manage.py createsuperuser
```

访问 `http://localhost:8080`，管理员通过 `/admin/` 管理账号。支持用户自助注册并立即启用；新账号固定为普通用户，可读取共享企业知识，不能进入管理员后台。内网既有安装的绑定路径与发布流程见 [运行说明](docs/operations-v02.md)。

Agent 默认通过 Chat Completions 调用现有火山 Kimi，由应用控制对话与工具循环、账号、会话、企业知识、确认和后台队列。固定版本 Codex App Server 0.163.0 保留为显式可选运行层，只获得业务工具，不开放终端或用户文件环境。搜索由独立 SearXNG 容器提供，后台任务负责公开 HTTPS 来源读取。公共搜索仅接受预定义技术词及受限制的芯片型号，内部资料通过必要片段用于企业问答。

```dotenv
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_API_KEY=<方舟 API Key>
LLM_MODEL=kimi-k3-1-pro-261024
AGENT_RUNTIME=chat
AGENT_SEARCH_ENGINES=google cse
AGENT_WORKERS=50
AGENT_MAX_STEPS=16
AGENT_TURN_SECONDS=300
AGENT_MODEL_TIMEOUT=120
# 当前火山 Kimi 的 Chat Completions 参数
LLM_THINKING=disabled
LLM_TEMPERATURE=0.6
```

修改模型配置后重新创建 backend、worker、agent-worker。Responses 基础测试与真实 Codex 动态工具调用已通过，但 Codex 完整调研曾多次达到 300 秒上限。相同模型与业务工具的 Chat 方式完成了追问、调研、修正和企业问答，因此按已确认的体验优先原则作为默认。`AGENT_RUNTIME=codex` 可显式选择；运行失败不会自动切换提供方或协议。

当前搜索使用验收中返回有效结果的 `google cse` 引擎；可用 `AGENT_SEARCH_ENGINES` 配置 SearXNG 引擎名称。批量查询使用精确型号，标题或 URL 不匹配的结果不会作为该候选证据。完成一批候选核查后直接整理首份结果及证据缺口，进一步查询由后续对话继续。外部引擎仍可能限流或变化，需要持续维护。

## 验证与边界

v0.2.6 发布镜像已通过 82 项后端测试、3 项注册/登录浏览器检查及 TypeScript/Vite 构建；v0.2.5 另有 5 项工作空间浏览器检查，覆盖账号隔离、持续对话、停止、确认、历史、权限冲突和资料格式。真实公开搜索、官方 PDF 读取、Ark Responses 和 Codex 工具调用分别通过。注册更新版本为 v0.2.6；完整线上组合的验收报告由发布脚本生成，见运行说明与实现状态。

v0.2.5 服务器实测：200 个合成账号、10,000 份文字资料、50,000 片段，50 个并发检索全部正确，P95 2.432 秒；另行运行的 50 个真实模型与联网调研任务全部成功，P50 83.46 秒、P95 118.50 秒。并发调研覆盖五类视觉需求、共同三款候选与公开资料缓存，合成文字不能代表实际企业 PDF/表格分布，也不是任意负载 SLA。其他复测曾出现一次模型 120 秒超时，5 并发阶段最慢 191.80 秒；详细成功数和失败记录均保留在发布报告。

当前不包含扫描件/OCR、企业系统自动同步、模型部署到芯片或实机性能验证。单文档最多 10 MiB；网络 PDF 最多读取前 20 页且输出有长度上限，复杂表格需核对原件。搜索引擎可能限流或出现验证码；失败会保留输入，不以虚构参数填补。1–3 分钟首份结果是体验目标，尚未承诺为 SLA。

## 开发检查

```bash
docker compose exec backend python manage.py test core.tests assistant.tests
cd frontend
npm ci
npm run build
# Playwright 测试使用本地隔离账号 ui-test，不对生产站点运行
npm run test:e2e
```

Vite 默认代理 `127.0.0.1:18080`，可通过 `DEV_BACKEND_URL` 覆盖。Codex 原始许可证与声明保存在 `licenses/codex/`，镜像内也包含相同文件。该项目未 fork Codex 源码，业务代码与开源运行层分离维护。
