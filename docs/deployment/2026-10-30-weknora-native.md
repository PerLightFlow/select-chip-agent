# 原生 WeKnora 上线记录

2026-10-30，原生 WeKnora v0.9.0 已上线至 <http://192.168.85.199:8080>。原生中文登录页面已在浏览器确认；登录 API 返回 `registration_mode=invite_register`。

## 已完成

- 使用专用密钥建立 SSH 复用连接 `/tmp/chipagent-native-20261030.sock`，ControlPersist 为 2 小时；服务器的 `sudo -n /usr/local/sbin/chipagent-release` 入口验证通过。未修改服务器 sudoers。
- 七个原生服务使用独立 Compose 项目 `weknora-native`，配置及数据位于 `/data/solexai/yongjun/weknora-native`。
- 配置企业研发知识空间、原生管理员、公共知识库、火山 Kimi、本地 `qwen3-embedding:0.6b`、SearXNG、两个原生自定义智能体及自动 Wiki。
- 验证前端资源与 API 代理、真实 Kimi 回复、搜索提供方、原生 Markdown 上传、独立向量/关键词召回，以及 Wiki 生成和源文档引用。合成验收知识库已删除。
- 验收通过后切换 8080；旧 Compose 项目 `select-chip-agent-yongjun` 与 `select-chip-weknora` 的运行容器已停止。未迁移旧账号、聊天、资料或项目卡片；旧数据卷仍保留。
- 部署边界、回退、凭据输出与重启就绪等待的本地测试共 16 项通过。

## 故障处理边界

先前 `ssh -t` / `sudo bash` 的启动方式与专用密钥及免密入口不匹配，已修正为无 PTY 的专用发布入口。

app 首次重启后的初始化曾报通用错误，但未保留具体异常。后续使用相同配置脚本完成初始化，脱敏诊断报告确认各配置接口均成功。另用模拟连接提前关闭的测试复现了就绪等待未重试 `RemoteDisconnected` 的问题，并修复；这证明等待逻辑存在缺口，不能单凭它断定先前服务器错误的唯一根因。修正后的完整发布与真实验收通过。

## 发布证据

- 服务器发布目录：`/data/solexai/yongjun/select-chip-agent/releases/weknora-native-a81241f147ef15f0`。
- 已执行归档 SHA256：`a81241f147ef15f0aaea52a0e94eae30fd9ffc44b4aabbd43f7ced601a412e13`。
- 服务器部署根目录内的 `acceptance.json`、`active.json`、`images.lock.json` 分别记录验收、切换与镜像。旧回退容器记录在清理时归档为 `cutover.before-legacy-cleanup-20261030.json`，已不能用于直接恢复旧容器。
- 本机归档目录：`/home/s5376/yongjun/work/proj/SLSelectChipAgent/work/weknora-native-release-20261030`；其中 `acceptance.json` 与 `active.json` 已从服务器回收，均不含凭据。
- 本机诊断报告：`work/weknora-native-diagnose-20261030/diagnostic.json`（相对外层工作区），只包含接口、响应结构和完成状态。

管理员邮箱为 `admin@weknora.local`。初始密码和员工邀请仅在本人终端运行以下脚本查看，不应贴到聊天或提交进 Git：

```bash
bash /home/s5376/yongjun/work/proj/SLSelectChipAgent/work/weknora-native-release-20261030/show-login-from-pc.sh
```

该脚本只读取当前发布目录中操作账号可读的最小登录信息，不重启或重新部署服务。初始密码在用户修改后不再代表当前密码；邀请过期后由管理员在原生界面创建新邀请。

## 旧服务清理

2026-10-30，经用户授权，已移除两个旧 Compose 项目 `select-chip-agent-yongjun` 与 `select-chip-weknora` 的 12 个已停止容器，以及 `select-chip-agent-yongjun_default`、`select-chip-knowledge` 两个专属网络。

清理了 `select-chip-agent-yongjun/` 下不再被任何容器引用的 17 个旧镜像标签。按全部容器的实际镜像 ID 检查共享引用，保留当前服务使用的镜像；未执行全局 prune、强制删除或卷删除。镜像层共享，因此标签大小不能直接相加作为释放空间。

清理前归档 `cutover.json`，使旧发布包的直接 rollback 入口在停掉前端前因缺少回退记录而退出。旧容器快速回退已退役；如需恢复旧系统，必须单独制定恢复部署，使用保留的 Compose、数据及发布包重新创建容器。

保留全部旧数据目录、Docker 卷、源码、配置和备份。旧项目目录内的 `docker-client/`、发布器工作目录、原生发布包及 `operator/` 登录信息仍有运维用途，因此没有删除整个 `select-chip-agent` 目录。

清理后复核：两个旧项目的容器和网络均为零；原生七个容器 ID 未变且全部运行，配置健康检查的服务均健康；网页、静态资源、API 代理和后端健康接口通过；其余既有容器的运行状态未变；免密发布入口仍通过检查。

- 服务器清理包与审计报告：`/data/solexai/yongjun/select-chip-agent/releases/weknora-legacy-cleanup-20261030/cleanup-report.json`。
- 本机报告：`/home/s5376/yongjun/work/proj/SLSelectChipAgent/work/weknora-legacy-cleanup-20261030/cleanup-report.json`；同目录保留实际执行脚本及校验清单，报告不含凭据。

## 尚未验收

200 个账号、50 人同时调研、10,000 份资料的容量目标，以及多用户越权、真实芯片调研质量和扫描件 OCR，均未在本次基础上线验收中验证。不得把七个容器正常或合成文档验收通过视为这些指标已经达标。

## Kimi 流式聊天温度兼容修正

2026-10-30，原生“快速问答”启用思考时出现 `temperature only 1 is allowed`。已用独立合成会话在同一 `knowledge-chat` 流式接口复现，未向用户原对话写入消息。原因是部署模板固定 `temperature=0.6`，而原生智能体可按请求开启思考，覆盖模型的默认非思考设置。

对当前 `kimi-k3-1-pro-261024` 的真实 Ark 流式接口分别测试：思考开启时 `0.6` 被拒绝、`1` 成功；思考关闭时 `1` 被拒绝并提示只允许 `0.6`；两种模式省略温度均返回 HTTP 200 和实际答案。

通过原生模型 API 仅修改兼容参数为 `supports_temperature=false` 并删除 `fixed_temperature`，保留凭据和其他配置。此开关让 WeKnora 省略采样参数，使用提供方默认值。无需重启，修改前的模型配置只保存在服务器 `weknora-native/model-temperature-before-20261030.json`。本地部署模板同步修正，后续首次部署不会重新固定该模型的温度。

已完成的线上验收：快速问答默认思考和显式关闭思考两条流均返回 `OK`，无 `error` 事件；七个原生服务持续运行。补查智能推理时测试流长时间未结束，已停止该合成调用并删除测试会话；该模式与未执行的后续芯片调研检查不能计为通过。旧的四项验收计划报告因此仍保留 `passed=false`，这不代表模型配置未生效。

部署验收已补充原生流式路径，要求实际 `answer` 帧、`complete` 事件且无 `error`，防止完成事件包含错误文本仍被误判成功。原有验收只测试非思考的非流式模型 debug 调用，因此未覆盖这次故障。

最终使用新增验收函数再次验证当前原生快速问答：默认思考与显式关闭思考均收到实际 `OK`、完成事件、零错误，前端资源与 API 代理也通过。该函数在终止事件后不等待连接 EOF，并对 heartbeat 设置总时限；异常时停止并删除自己的合成会话。部署与流式解析共 30 项本地测试通过。

- 本机修正与证据：`work/weknora-temperature-fix-20261030/`（相对外层工作区），含提供方参数矩阵和实际流式检查结果。
- 服务器修正包：`/data/solexai/yongjun/select-chip-agent/releases/weknora-temperature-fix-20261030/`。
- 最终快速问答回归报告：本机 `work/weknora-temperature-verify-20261030/verification.json`，服务器对应 `select-chip-agent/releases/weknora-temperature-verify-20261030/verification.json`；该限定范围报告为 `passed=true`。

## 前端定制

当前使用官方前端镜像。后续可以在 WeKnora Fork 的 `frontend/` 中修改 Vue 3 / TypeScript 界面，独立构建并替换前端镜像；涉及新增 API 或权限规则时需后端配合。具体命令见 [部署说明](../../deploy/weknora-native/README.md#后续修改原生前端)。
