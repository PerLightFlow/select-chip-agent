> 当前网页与 API 已更新为 v0.2.6（2026-10-29 14:55）。用户可自行注册并立即启用，账号固定为普通用户。发布包为 `releases/signup-v026`，重发命令为 `sudo bash releases/signup-v026/apply.sh`；注册和 HTTP 验证结果在其 `results/`。本次备份为 `backups/signup-20261029-145452`，可恢复 v0.2.5。worker/agent-worker 未修改，仍使用 v0.2.5。下文保留其调研运行与并发验收说明。

# 内网运行与验证

服务器：`solexai1@192.168.85.199`。业务目录：`/data/solexai/yongjun/select-chip-agent`。镜像与运行层沿用已获授权的 Docker 存储 `/data/dockerdata`。站点为 `http://192.168.85.199:8080`，保留既有账号，管理员入口 `/admin/`。

## 当前运行版本（2026-10-29 15:19）

网页 `web:chat-controls-v027`，HTTP 后端 `backend:signup-v026`，两个 worker `backend:reframing-v02.5`，搜索 `search:reframing-v02`。健康接口版本为 0.2.6。网页更新含最近对话删除与完成后隐藏进度；自助注册继续可用。

最新网页补丁为 `releases/chat-controls-v027`。结果位于其 `results/`；备份 `backups/chat-controls-20261029-151939` 仅包含旧 Compose 和网页源码。此补丁只重建 web，其他服务容器不变。回退网页只需恢复该备份的 Compose 并运行 `sudo deploy/compose up -d --no-build --no-deps web`；不要用它恢复数据库或环境文件。

以下保留 v0.2.5 模型运行及验收说明。

## v0.2.5 发布记录

当前发布包为 `releases/reframing-v02.5`，含镜像、源码、Compose、SHA-256 校验、发布和隔离验收脚本。后台镜像 `backend:reframing-v02.5`，网页沿用 `web:reframing-v02.1`，搜索沿用 `search:reframing-v02`。

默认运行层为 Chat Completions，模型仍为服务器已配置的火山 Kimi。配置为 `AGENT_RUNTIME=chat`、`AGENT_SEARCH_ENGINES=google cse`、`AGENT_WORKERS=50`、`AGENT_MODEL_TIMEOUT=120`、`AGENT_TURN_SECONDS=300`。Codex 可显式选择，不在失败时自动切换。单次模型等待参考整轮剩余预算；120/300 秒是执行控制参数，不是响应时间承诺。

账号、数据库和文档存储继续使用原挂载。模型密钥只在服务器 `.env`，不进入源码、网页或报告。搜索不映射公网端口。

```bash
sudo bash /data/solexai/yongjun/select-chip-agent/releases/reframing-v02.5/verification/apply.sh
```

重复执行会重新发布并消耗模型额度进行验收。脚本校验包、等待现有隔离验收结束、备份源码和运行配置，再更新镜像；健康失败恢复原运行配置。首次 v0.2 发布另保留数据库备份，本次修正包不重新生成业务数据库快照。

本次上线时间为 2026-10-29 13:49（Asia/Shanghai），备份目录为 `backups/reframing-fix-20261029-134818`。该备份对应 v0.2.4。后续重发会生成新的目录，应以对应发布日志为准；`deploy/last-reframing-backup` 仍指向首次 v0.2 备份，不能据此认定是最新修正包备份。

## 验收报告

最终并发验收日志为 `releases/reframing-v02.5/acceptance-research.log`，报告位于同目录 `results-research/`；摘要为 `final-acceptance-v025.json`。多轮功能证据为 `workflow-reviewed.json`，完整复测记录在 `results-verified/`（其中一次模型调用超时）。最初的 `results/` 保留用于诊断：实际企业回答已正确引用文档，但原校验器依赖未保留的文档 ID，导致误报失败。修正校验器后改为核对准确的文档版本 URL；验证时只读挂载该管理命令，业务镜像不变。

- `status.json`：是否结束、退出码及合成数据库是否已清理。
- `../workflow-reviewed.json`：首次真实追问、候选调研、条件修正、项目芯片与分工问答及校验修正说明。
- `live-5.json`、`live-50.json`：真实模型任务的耗时、来源、用量、进度和失败原因。
- `database.json`：200 账号、10,000 份合成文字资料、50,000 片段的独立检索测试。
- `resources.csv`：临时 worker 的 CPU、内存和进程采样。

再次单独验收可执行 `sudo bash releases/reframing-v02.5/verification/launch.sh`（在业务根目录执行），会消耗模型额度并更新 `results-verified/`。重发使用上方 `verification/apply.sh`，会校验原始包与验收修正文件，并自动调用修正版验收。最初的发布脚本和报告保留作历史证据。

验收依次扩大负载，前一阶段失败就停止；测试卡片和文档不写入业务数据库。临时 worker 和测试数据库结束时自动清理，结果保留。`peak_running_tasks` 仅表示同时认领的任务，必须结合成功数、正文和来源判断。

调研自动通过条件包括完整对比正文、指定候选和已读取来源的链接，只有进度说明不算通过。企业问答必须同时引用项目卡片与对应文档。答案准确性仍需人工检查。并发场景使用五类视觉需求、同组三个候选及公开资料缓存；合成资料不代表实际企业 PDF/表格分布，不能扩大解释为任意负载 SLA。

## 故障与回退

模型错误会保留本轮输入。HTTP 429 表示模型服务限流；响应超时与其他 HTTP 拒绝分别显示。公开来源失败时应交付已有依据及未知项，后续对话可继续查证；不要因缺资料填补虚构参数。

需要回退时，先确认发布日志中的备份目录，将其中的 `compose.yaml` 和 `env` 分别恢复到 `deploy/compose.yaml` 和 `.env`（权限 600），再运行 `sudo deploy/compose up -d --no-build backend worker agent-worker web`。只做运行版本回退时不恢复数据库快照，避免覆盖上线后的会话与企业知识。恢复旧源码可使用同目录 `source.tar.gz`，应先核对有无后续人工变更。

旧版表和新增 assistant 表相互独立；若回退到 v0.1，应另停止新 agent-worker 和 search，按照首次发布备份恢复对应配置。不得让新 worker 与旧运行配置混用。

本次最新结果：真实调研 5/5、50/50 成功，50 并发 P50 83.46 秒、P95 118.50 秒；200 合成账号/10,000 文字资料检索 50/50 正确，P95 2.432 秒。另一次流程复测的 120 秒模型超时如实保留。
