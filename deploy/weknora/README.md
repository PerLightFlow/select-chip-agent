# WeKnora 接入：第一阶段运行说明

本目录部署独立 WeKnora v0.9.0 服务及本地 `qwen3-embedding:0.6b`。现有账号、项目卡片、私人聊天和公开调研保持原有职责。本阶段实现已确认文档同步、混合原文检索和版本引用；Wiki 的生成和问答接入尚未开放。

2026-10-30 按用户要求，正式环境已从 `shadow` 直接切换至 `weknora`，不再进行对照查询，也不在服务异常时静默回退旧检索。尚未完成索引的已发布资料会明确提示等待；草稿仍需确认后才共享。

## 部署

部署前执行后端测试、前端构建及 Compose 校验。服务器数据固定在 `/data/solexai/yongjun/weknora`，与现有 PG16 数据卷独立。镜像仍使用已获准复用的 Docker 公共存储。

```bash
sudo bash deploy/weknora/start.sh /data/solexai/yongjun/weknora
```

脚本保留已有密钥，拉取并锁定实际镜像 digest，再启动独立服务、下载向量模型、创建集成账号及公共知识库。项目自带的 Docker Compose 插件位于 `/data/solexai/yongjun/select-chip-agent/docker-client`，脚本在系统插件不可用时复用它。脚本不改动现有应用的 Compose、`.env` 或数据。

管理 API 仅绑定 `127.0.0.1:18081`。数据库、Redis、docreader 和模型服务不发布宿主端口。配置与 `bootstrap.json` 含凭据，应保持 0600，不加入 Git 或日志。模型初次下载需要联网，日常 Embedding 在本地执行。

2026-10-30 真实接入确认了三项 v0.9.0 约束：注册密码为 8–32 位且必须包含字母与数字；创建 API Key 时使用 `data.token`（开启存储加密时 `data.api_key` 可能是加密值）；带 KB 白名单的 Key 会拒绝 `knowledge_ids` 检索。因此本应用使用独立集成租户，读取 Key 仅授予 `retrieve`、不设置 KB 白名单；写入 Key 仍限定指定 KB。两把 Key 均不授予 `full_access`。Django 始终只发送当前发布版本的文档 ID，并核验回包和回答交付时的版本状态。不要在此专用租户存放其他应用的资料。

同次实测发现，KB 级关闭问题生成会添加一段 ParadeDB 不支持的检索过滤 SQL。当前兼容配置将 KB 的 `question_generation_config.enabled` 设为 `true`，**每次应用上传仍通过 `process_config` 明确将问题生成、摘要、图谱和多模态设为关闭**；WeKnora 尚未配置聊天模型。此配置仅适用于本应用专用租户，不能从 WeKnora UI 或其他程序直接上传资料。启用 Wiki/聊天模型前需要重新验证该约束，优先在上游修复后恢复 KB 级关闭。真实验收必须分别通过向量、关键词查询，不能只依赖混合查询的 HTTP 200。

单独准备本地测试环境时：

```bash
python3 deploy/weknora/prepare.py --root /tmp/chipagent-weknora-dev --network chipagent-weknora-dev
docker compose --project-directory /tmp/chipagent-weknora-dev up -d --wait
docker compose --project-directory /tmp/chipagent-weknora-dev exec -T embedding ollama pull qwen3-embedding:0.6b
python3 deploy/weknora/bootstrap.py --state /tmp/chipagent-weknora-dev/bootstrap.json
```

不要将生产资料上传到本地验收环境；真实 API 验收先使用合成文档。首次下载时间与中文召回、50 并发吞吐需要单独记录，不根据模型大小推断已达标。

## 接入应用

1. 备份应用数据库、原件、`.env` 与当前 Compose；部署包含 `assistant.0003` 的后端。
2. 在应用服务端 `.env` 配置 `WEKNORA_SYNC_ENABLED=1`、`WEKNORA_BASE_URL=http://weknora:8080`、`WEKNORA_READ_KEY`、`WEKNORA_WRITE_KEY`。Key 从服务器 `bootstrap.json` 读取，切勿粘贴到聊天或前端配置。
3. 保持 `KNOWLEDGE_BACKEND=legacy`，将 `deploy/compose.knowledge.yaml` 与应用 Compose 合并，让 backend、agent-worker、knowledge-sync 加入知识服务网络。服务器原有自定义镜像/挂载配置必须保留，不能直接覆盖。
4. 为每个项目建立对应知识库；公共库用 `common`，项目库用 `project:<本地项目ID>`。重复运行 bootstrap 会复用库并更新服务 Key 的范围：

```bash
python3 deploy/weknora/bootstrap.py --state /data/solexai/yongjun/weknora/bootstrap.json --scope project:123
```

5. 在应用后端容器中绑定外部 KB，并补录历史资料：

```bash
python manage.py weknora_sync bind --scope common --kb-id <公共库ID>
python manage.py weknora_sync bind --scope project:123 --kb-id <项目库ID>
python manage.py weknora_sync backfill
python manage.py weknora_sync status
```

6. 启动 `knowledge_sync_worker`，确认已发布资料全部完成索引，然后切到 `weknora`。已安装 v0.3.0 的服务器可运行 `sudo bash deploy/weknora/activate.sh`，脚本会检查凭据和资料状态、备份配置、同步重建应用服务并验证实际检索分支，失败时恢复原配置。`shadow` 仍可用于显式调试，但不是切换前置条件。新发布使用 `apply-app.sh` 时默认采用 `weknora`。

`backfill` 只处理已经确认发布的版本，可重复运行。新版本确认与旧版本撤回在同一个 Django 事务中写同步任务；网络失败不回滚业务发布。对于尚未完成新索引的范围，WeKnora 模式明确提示等待，不将部分资料结果当作完整搜索。空文档范围不会发起无过滤的全库查询。

## 状态与恢复

业务发布状态与索引状态分别记录。`source_ready` 仅说明原文索引可用；`wiki_state=disabled` 不代表 Wiki 已生成。本阶段必须关闭 KB 的 Wiki/图谱开关，绑定和上传时会检查。

- `queued/running/polling`：待同步、处理中、等待远端索引。
- `retry`：网络或服务故障，延迟重试，达到上限后 `blocked`，避免无限忙循环。
- `uncertain`：上传可能成功但响应丢失。通过请求时的唯一文件名对账，禁止直接重复 POST。
- `blocked`：需要处理绑定、凭据、重复资料或解析故障；列表显示经过清理的错误，不暴露供应商响应。
- `deleted`：远端原文已删除或从未上传。本阶段不代表未来 Wiki 的撤回也已完成。
- `deleting`：远端已接受异步删除，继续等待 GET 返回 404；30 分钟未完成则转为 `blocked`，不会重复提交已确认的删除任务。

上传者或管理员可以从文档预览中重试，也可在后台执行：

```bash
python manage.py weknora_sync retry --version-id <本地版本ID>
```

解析明确失败时，重试请求远端 reparse；普通网络故障只继续同步/轮询。已经开始但无法确认结果的上传保持原始标识，重试只对账。若长期找不到对应文件，管理员需检查远端任务/文件列表后处理，不能盲目清空 `upload_started_at`。内容重复导致的 409 不会自动将不同业务版本绑定到同一远端记录。

worker 的数据库租约允许崩溃恢复，PostgreSQL advisory lock 防止旧 worker 尚在执行时重复上传。撤回立即影响本地允许列表；远端删除失败不会恢复旧版本可见性。长回答交付前还会检查引用版本。

## 回退与当前边界

将 backend、agent-worker 的 `KNOWLEDGE_BACKEND` 改回 `legacy` 并重建相应容器即可回退检索。旧 Passage 索引继续随所有新资料生成，所以回退仍遵守最新发布/撤回状态。必要时停止 knowledge-sync；不删除新旧数据卷，也不逆向撤销数据库迁移。

备份包括 Django 原件/数据库、WeKnora 数据库/文件、Redis、模型目录、`.env` 中加密主密钥及 bootstrap 凭据。备份只能视为已生成，直到恢复演练通过才能宣称可恢复。

尚未包含：Wiki 页面工具/UI、严格 Wiki 生成代次切换、扫描件的确认前新解析流程、全量远端索引定期对账、1 万资料/50 并发验收。项目新建后的 KB 建立目前由运维命令完成，未绑定的项目资料明确显示待处理。

参考：[接入设计](../../docs/design/2026-10-29-weknora-integration.md)、[固定版本 API 证据](../../docs/research/2026-10-29-weknora-api-evidence.md)、[Ollama 模型](https://ollama.com/library/qwen3-embedding:0.6b)。
