# Select Chip Agent

面向嵌入式产品的需求分析、芯片选型与公共文档混合检索。技术栈为 Django / DRF、React / TypeScript、LangGraph、PostgreSQL / pgvector。

这是首个可运行开发版本。正式芯片库默认为空；**尚未完成 ESP32 与 Rockchip 全部在售型号的数据建设**。项目不会把虚构数据或未审核资料用于正式推荐。

## 已实现的流程

- 登录后创建项目，输入自然语言需求，通过可配置的对话模型提取建议；用户确认可编辑约束后执行选型。
- Python 规则逐项输出通过、不通过或待验证。缺失证据、单位不符、适用条件不同不会判为通过。
- 公共知识库统一共享已发布数据，普通用户不能写入知识，项目与报告按账号归属访问。
- Django Admin 维护芯片参数、逐项证据、算法适配记录和文档版本；记录管理操作与历史选型快照。
- PDF / HTML / Markdown / TXT 资料解析，持久化任务队列，人工审核后发布；版本切换与撤回立即影响新检索。
- 中文分词关键词搜索 + pgvector 精确向量搜索 + RRF 排名融合，支持型号、SDK 和任务过滤，并返回原文定位。
- Embedding 或对话模型不可用时明确展示降级状态，不把关键词匹配伪装成语义检索。
- CSV / XLSX 型号目录导入命令，默认预览，确认应用后导入未发布草稿。
- 两款独立的**虚构演示芯片**，通过页面开关显式启用。

模型图检查、量化转换、训练与实机接入不在当前范围内。当前报告采用确定性模板，LLM 用于需求提取；语义检索结果以证据卡片呈现。

## 启动

需要 Docker Engine 与 Compose，能够拉取镜像和安装依赖。先复制配置并设置随机密钥：

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
# 将生成值填入 .env 的 DJANGO_SECRET_KEY，另设 POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py seed_demo
```

打开 http://localhost:8080 。管理后台位于 http://localhost:8080/admin/ 。使用刚创建的账号登录；管理员在后台创建普通用户，不开放匿名注册。

默认仅监听本机 127.0.0.1:8080。用于远程访问时部署 HTTPS 反向代理，设置实际 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` 与 `COOKIE_SECURE=1`。数据库和文档存储使用独立持久化卷。

## 模型服务

在 `.env` 中分别配置对话服务与文本向量化服务，兼容 `/chat/completions` 与 `/embeddings` 请求格式。Base URL 需包含服务所要求的版本前缀，例如 `/v1`。不会自动选择或购买模型服务。

```dotenv
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
EMBEDDING_BASE_URL=https://your-provider.example/v1
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=...
EMBEDDING_REVISION=1
EMBEDDING_DIMENSIONS=1024
```

维度必须与服务实际输出一致。向量模型、维度、服务地址、修订号与分段规则共同决定索引配置，查询不会混用不同配置的向量。使用工程师标注的中英文样本选择模型，并校准 `EMBEDDING_MAX_DISTANCE`；默认阈值只是初始配置，尚不是实测结论。

修改配置后执行 `docker compose up -d --force-recreate backend worker`。没有配置 Embedding 时，演示资料可关键词查询；正式资料索引默认失败并明确提示。仅在有意接受降级时设置 `ALLOW_KEYWORD_ONLY=1`。

## 录入真实资料

1. 在管理后台创建 Document，填写名称、来源 URL；URL 仅保存为来源，不自动从服务器抓取。
2. 创建 DocumentVersion，填写版本、适用型号数组和 SDK 版本，上传资料或粘贴正文。
3. 使用“生成待审核索引”操作，Worker 完成解析、分段及向量化后变为 ready。
4. 人工核对提取文本、适用范围、表格和脚注，使用“审核通过并发布”。原始资料和新旧版本保留。
5. 建立 Chip 与 Fact；每个已确认参数绑定相应 Chunk，参数单位及条件与需求一致时才参与硬筛选。证据中适用型号必须包含该芯片。
6. 核验型号状态后发布芯片。仅有官网目录页面不等于已确认在售。

HTML 合并单元格、扫描件、提取不可靠的 PDF 页面需先人工整理或 OCR。当前采用保守分段，保留完整表格块；尚未实现自动跨页表格重建。数据库默认使用精确向量查询，规模扩大后再依据评测引入近似索引。

批量导入型号目录（字段见 `docs/catalog-template.csv`）：

```bash
docker compose cp docs/catalog-template.csv backend:/tmp/catalog.csv
docker compose exec backend python manage.py import_chips /tmp/catalog.csv
docker compose exec backend python manage.py import_chips /tmp/catalog.csv --apply
```

导入不会覆盖已有型号，不会自动核验供货、不自动发布，也不会把导入文件当成参数证据。

## 测试与本地开发

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# 在当前 shell 配置 DJANGO_SECRET_KEY、POSTGRES_*；普通命令不会自动读取根目录 .env
python manage.py migrate
python manage.py check
python manage.py test core.tests -v 2
python manage.py runserver 127.0.0.1:8000
# 另一个终端运行：python manage.py worker
```

```bash
cd frontend
npm install
npm run dev
```

无第三方依赖的规则测试可单独执行：

```bash
cd backend
python -m unittest core.tests.test_domain -v
```

GitHub Actions 使用真实 PostgreSQL + pgvector 验证迁移、版本过滤、撤回、账号隔离、CSRF、规则与向量查询，再执行前端 TypeScript 检查和生产构建。向量测试使用受控向量夹具，不代表已验证真实 Embedding 模型质量。CI 保存依赖解析结果与前端构建产物。

## 交付边界与后续任务

详细范围和剩余工作见 [docs/implementation-status.md](docs/implementation-status.md)。全量目录、真实语义检索评测、跨页复杂表格、UI 批量差异审核、正式邀请链接、运行配额与备份恢复演练仍需继续完成。依赖目前按兼容范围约束，首轮 CI 的解析产物用于后续锁定，不声称已经完整锁定供应链。
