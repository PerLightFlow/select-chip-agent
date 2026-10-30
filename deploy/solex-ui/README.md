# SOLEX 前端独立发布

只替换 `weknora-native` Compose 项目的 `frontend` 服务。后端、数据库、模型服务、文档解析、Redis、搜索与原有数据均沿用当前实例。此目录仅包含部署工具；完整上游及 SOLEX 前端源码位于仓库 `weknora/`。

## 准备

1. 在 `weknora/frontend` 使用仓库锁文件执行 `npm ci`、相关测试、`npm run build`。
2. 将已经审查的 SOLEX 前端源代码记录到 Git，取得完整提交 SHA。
3. 在仓库根目录打包一个新发布目录：

```bash
python3 deploy/solex-ui/prepare-release.py \
  --dist weknora/frontend/dist \
  --source-revision FULL_GIT_COMMIT \
  --output /absolute/path/to/new-release-directory
```

输出包含 `release_id`、独立镜像标签、构建产物 SHA256、源码提交、`SHA256SUMS`。打包器拒绝覆盖已有目录以及包含符号链接的产物。运行镜像固定为当前服务器已安装的原生前端 digest：

`wechatopenai/weknora-ui@sha256:df26705d866997db07f3da78dabedc4f594b383566a3996810c166a5c6bee393`

Dockerfile 保留该镜像的 Nginx 代理模板与入口脚本，完整清除旧静态目录后复制新 `dist`。入口脚本继续生成运行时配置，沿用 API、流式对话、WebSocket、文件与嵌入页面代理协议。旧 upstream 文件名或内部协议标识不改动。

## 运行

通过已有 SSH 连接上传发布目录内容至：

`/data/solexai/yongjun/select-chip-agent/releases/RELEASE_NAME/`

`RELEASE_NAME` 建议采用打包器输出的 `release_id`。已有服务器免密发布工具是唯一入口：

```bash
sudo -n /usr/local/sbin/chipagent-release apply RELEASE_NAME
```

`apply.sh` 校验文件清单并复用原生发布锁；`deploy.py` 执行：

1. 检查当前 7 个服务、保存不含凭据的服务状态。确认当前前端镜像与 `.env` 一致。
2. 用本机已有的固定 runtime 镜像构建 SOLEX 镜像；禁止构建时网络访问，不拉取镜像。
3. 在独立临时容器和 `127.0.0.1:18084` 启动 canary。仅复制前端运行时白名单参数，沿用独立 `weknora-native` 网络访问 `app`。
4. 检查 `/login` 的 SOLEX 标题、编译后 JS/CSS 资源、`/api/v1/auth/config` 代理及注册策略一致。
5. 仅改 `.env` 的 `WEKNORA_UI_IMAGE` 一行，然后执行 `docker compose up -d --no-deps --no-build --pull never frontend`。
6. 复查 8080 入口和另外 6 个服务的容器 ID、镜像、启动时间和重启次数；成功或回退后移除自己的 canary。

发布失败后自动恢复原 `.env` 和前端镜像，再确认旧入口与后端服务正常。若 `.env` 在发布过程中被其他操作改动，脚本停止以免覆盖新配置。重复发布同一成功版本不会覆盖首次回退备份。

根目录 `ui-releases/RELEASE_ID/` 保存验证结果与 root-only 的 `env.before`、`env.after`；环境文件含现有服务器配置，不应下载、打印或加入 Git。无凭据的当前前端记录位于：

`/data/solexai/yongjun/weknora-native/solex-ui-active.json`

`deploy.py canary` 可在同一发布锁下由已授权的管理员单独运行，验证后保留回环 canary；它不改公共入口。正式 `apply` 会重新验证并接管同版本 canary。

## 验证范围

自动检查覆盖入口、静态资源、API 代理与其余容器不重建。它不能替代浏览器中的登录、邀请注册、工作台、智能体、知识库和手机布局验收，也不代表模型质量、50 人并发或万份文档容量通过。

2026-10-30 只读调查：服务器没有 `node` 构建镜像。此方案发布阶段只消费已构建 `dist`；如需转服务器构建，应另行准备固定 Node 版本，继续使用完整源码中的 `package-lock.json`，不要使用正在运行的业务容器安装依赖。
