# 原生 WeKnora 部署包

基于官方 v0.9.0 前端、后端与 Docreader 镜像。此目录仅包含部署、初始化和验收脚本，没有修改 WeKnora 应用源码，也没有自研 Agent 引擎。

## 当前状态

2026-10-30：原生 WeKnora v0.9.0 已通过真实链路验收并切换到 `http://192.168.85.199:8080`，浏览器已确认中文原生登录页。后续已按用户授权移除旧应用与旧知识后台的 12 个容器、2 个专属网络及 17 个无容器引用的旧镜像标签；数据、备份及仍需使用的发布工具保留。详见 [上线记录](../../docs/deployment/2026-10-30-weknora-native.md#旧服务清理)。

已通过执行权限审批建立可复用 SSH 连接，并验证专用免密发布入口。初始化曾在 app 重启后失败，原日志未保存具体异常；服务稳定后，原脚本的整个 configure 阶段已成功。补充了重启时连接提前关闭的回归测试与重试处理，并保留不含凭据的异常类型/代码行号。基础部署测试共 16 项通过，尚未完成容量验收。

后续修正：当前 Kimi 模型已取消固定采样温度，由 Ark 按思考模式使用默认值，解决原生快速问答的 `temperature only 1` 报错。部署模板同步修正，并增加原生流式聊天验收。详情及额外智能推理检查的限制见 [温度兼容修正记录](../../docs/deployment/2026-10-30-weknora-native.md#kimi-流式聊天温度兼容修正)。

## 部署结果

- 数据与配置：`/data/solexai/yongjun/weknora-native`，使用独立数据库和文件目录，不导入旧账号、聊天、资料或项目卡片。
- 使用现有 Docker 镜像存储。先复制现有向量模型文件到新模型目录；缺少模型时通过 Ollama 下载 `qwen3-embedding:0.6b`。
- 前端、后端、PostgreSQL/ParadeDB、Redis、Docreader、Ollama、SearXNG 共七个服务。SearXNG 独立于旧应用。
- 临时入口仅服务器本机可见：UI `127.0.0.1:18082`、API `127.0.0.1:18083`。检查通过后 UI 切到 `192.168.85.199:8080`。
- 模型凭据仅在服务器读取 `/data/solexai/yongjun/select-chip-agent/.env`，通过原生 API 存储；不复制到发布包或日志。
- 新建企业研发知识空间、原生管理员、公共知识库，启用自动 Wiki。公共库由管理员维护；Contributor 可以创建并维护自己的库，同空间成员可检索。
- 配置原生“芯片调研”和“企业知识问答”智能体；研究 Agent 开联网、关闭知识库和记忆；企业问答关闭联网。知识写入使用原生“知识维护助手”，执行权限为修改前确认。
- 采用原生邀请注册：管理员在成员管理界面发送邀请，员工通过链接自行注册后立即入组。邀请链接默认七天有效，失效后由 Owner 新建。普通登录页不提供无限制公开注册。
- 首次模型并发 8、Wiki worker 1、Embedding 并发 1、上传上限 50 MB。这些是起步设置，不能视为已满足 200 账号/50 人同时调研/10,000 份资料。

## 执行与证据

本机执行发布目录中的 `start-from-pc.sh`。它使用既有专用密钥 `~/.ssh/chipagent_solexai1_192_168_85_199`，以不分配 PTY 的新连接访问 `solexai1@192.168.85.199`，先检查免密入口，再上传校验后的发布包到 `select-chip-agent/releases/weknora-native-<摘要>`，执行 `sudo -n /usr/local/sbin/chipagent-release apply <发布名>`。无需修改 SSH 或 sudoers；不会尝试通用 `sudo bash`。

该专用密钥带 `restrict`，因此不能使用 `ssh -t`；服务器仅为 `chipagent-release` 提供 NOPASSWD，并未授权所有 sudo 命令。入口会保留原有 Docker 客户端配置。

步骤依次为：校验与准备、拉取并锁定镜像摘要、回环端口启动、初始化原生配置、合成资料验收、切换端口。首次注册后会重启 app，让官方 bootstrap 机制授予新账号系统管理员身份。

`acceptance.py` 会通过原生文件上传接口上传合成 Markdown，不传旧集成的 `process_config` 覆盖。分别验证向量/关键词召回、Wiki 完成及来源引用，并验证前端静态资源/API 代理、基本模型回复和搜索提供方连接。验收失败会保留证据，且不会停止旧系统。

只有这些检查通过且团队邀请配置成功，才会停止 `select-chip-agent-yongjun`、`select-chip-weknora` 两个已知 Compose 项目原先运行的容器。保留旧卷，不执行 `down -v`、镜像清理或全局 prune。切换后检查失败，会恢复之前运行的容器并将新前端退回回环端口。

证据均位于新部署根目录：

| 文件 | 内容 |
|---|---|
| `images.lock.json` | 实际拉取并使用的镜像摘要 |
| `acceptance.json` | 基础链路检查；容量、OCR、多用户隐私和调研质量标为尚未验收 |
| `cutover.json` | 首次切换时的旧容器 ID；旧服务清理后已归档为 `cutover.before-legacy-cleanup-20261030.json`，直接回退不可再用 |
| `active.json` | 仅在新入口检查通过后写入 |
| `admin.json` | 管理员凭据与邀请，0600，仅在本人终端查看 |

成功后，发布脚本在当次发布目录的 `operator/` 下生成验收结果和最小化登录信息。目录为 0700、文件为 0600，归 SSH 操作账号 `solexai1` 所有；原始 `admin.json` 仍仅 root 可读。向导只回收不含凭据的 `acceptance.json`、`active.json`；登录密码与邀请链接通过普通 SSH 仅在操作者终端显示，不写入部署日志，也不下载到本地仓库。重跑已成功的部署只重新导出这些结果，不重置账号或重启服务。

向量/关键词接口和部分管理 API 在 v0.9.0 有已知集成差异。本包依据固定版本源码编写，服务器真实执行结果才是最终部署证据。合成资料验收不替代真实项目问答、权限越权检查、工具调用质量与 50 并发/万份资料验收。

首次切换检查失败时，脚本会自动恢复尚未清理的旧容器。**当前服务器已完成旧服务清理，不能再执行旧容器快速回退。** 清理包已先归档 `cutover.json`，旧 `cutover.py rollback` 会在停止前端前因缺少记录退出。不要把归档记录复制回原路径后直接回退；恢复旧系统需使用保留的 Compose、数据及发布包另行部署。

## 后续修改原生前端

官方前端位于 `Tencent/WeKnora/frontend`，使用 Vue 3、TypeScript、Vite、TDesign。建议后续在自己的 GitHub Fork 中维护定制分支，保留 upstream 远程，当前部署先使用官方镜像。

在对应版本的 WeKnora Fork 根目录执行：

```bash
docker build -t perlightflow/weknora-ui:v0.9.0-custom1 frontend
```

将镜像送到服务器，修改新部署 `.env` 的 `WEKNORA_UI_IMAGE` 为自己的镜像引用，然后在新部署目录执行：

```bash
docker compose up -d --no-deps --no-build frontend
```

只修改样式、文案、Logo、布局或已有数据的展示时，可以只替换前端镜像。新增 API、业务流程或权限规则时需要后端配合。保持定制前端与后端 API 版本匹配；不要通过修改运行中的容器文件来维护长期定制。

项目主代码采用 MIT 许可，分发修改版时保留相应版权和许可声明，依赖遵循各自许可。

来源：

- [v0.9.0 官方 Compose](https://github.com/Tencent/WeKnora/blob/v0.9.0/docker-compose.yml)
- [前端 package.json](https://github.com/Tencent/WeKnora/blob/v0.9.0/frontend/package.json)
- [前端 Dockerfile](https://github.com/Tencent/WeKnora/blob/v0.9.0/frontend/Dockerfile)
- [空间与邀请 API](https://github.com/Tencent/WeKnora/blob/v0.9.0/website-docs/04-api/02-api-tenant.md)
- [主许可证与依赖许可](https://github.com/Tencent/WeKnora/blob/v0.9.0/LICENSE)
