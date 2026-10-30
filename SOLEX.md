# SOLEX 源码与开发入口

当前原生平台的完整源码位于 [`weknora/`](weknora/)，产品界面名称为 **SOLEX**。

这是直接纳入本仓库 Git 管理的完整上游源码，不是子模块、嵌套仓库或仅前端副本。根目录原有的 `backend/`、`frontend/` 是历史自研系统；新的界面修改应在 `weknora/frontend/` 中进行。

## 上游基线

| 项目 | 值 |
| --- | --- |
| 上游 | https://github.com/Tencent/WeKnora.git |
| 版本 | v0.9.0 |
| 上游提交 | `f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7` |
| 完整源码树 | `de9e8951de64824a2f654d8ff5ace37fe5672b23` |
| 纳入文件 | 5,870 个上游跟踪文件；逐文件内容、可执行位与符号链接已校验 |
| 本仓库基线提交 | `33001f3` |
| 发布归档 SHA-256 | `b6870da4beee43313e0cbead789d8ea49680c295e3e341938ac542a444631686` |

可通过 `git rev-parse 33001f3:weknora` 核对源码树。上游的许可证、第三方声明、后端、CLI、解析服务、测试、文档和构建文件均保留。产品定制放在后续独立提交中，便于比较与回退。

## 开发

```bash
cd weknora/frontend
npm ci
npm run dev
```

发布前执行 `npm run type-check`、相关测试和 `npm run build`，并验证桌面与手机布局。依赖锁文件使用上游版本，`node_modules/` 和 `dist/` 不提交。

常用位置：

- `weknora/frontend/src/views/auth/`：登录、邀请与空间初始化。
- `weknora/frontend/src/components/menu.vue`：工作台导航。
- `weknora/frontend/src/views/creatChat/`：新对话首页。
- `weknora/frontend/src/assets/solex/`、`assets/theme/solex.css`：品牌资源与全局主题。
- `weknora/frontend/src/views/settings/SolexHelp.vue`：站内帮助。
- `weknora/internal/`、`weknora/cmd/`：Go 后端。
- `weknora/docreader/`：文档解析服务。
- `deploy/solex-ui/`：现有原生部署的前端发布与回退脚本。

## Git 维护

`origin` 保持为 `PerLightFlow/select-chip-agent`，`weknora-upstream` 指向官方仓库。克隆本仓库即可取得完整源文件，不需要额外初始化子模块。Git remote 配置不会随克隆传播，后续需要追踪上游时执行：

```bash
git remote add weknora-upstream https://github.com/Tencent/WeKnora.git
git fetch --no-tags weknora-upstream refs/tags/v0.9.0:refs/remotes/weknora-upstream/v0.9.0
git diff 33001f3..HEAD -- weknora/frontend
```

升级上游应单开分支，先核对完整新版源码，再对照 SOLEX 定制提交处理冲突和验证。不要把上游根目录直接合并到当前仓库根目录。业务代码、部署配置、数据与运行凭据分开维护，服务端 `.env`、数据库、模型文件和账号凭据不加入源码。

## 品牌与兼容

界面统一为 SOLEX；存储键、API 字段、内置智能体 ID、消息协议及既有嵌入接口保留兼容。新嵌入代码使用 `solex-widget.js`，旧接口仍可工作。用户文档、模型回答和自定义名称不做全局文本替换。

现有 Docker 部署位于 `/data/solexai/yongjun/weknora-native`。界面改版只替换前端容器；模型配置、账号、知识库、Wiki 和其他服务保持现有数据。源码导入和界面构建通过不等同于后端全部测试或生产并发验收。
