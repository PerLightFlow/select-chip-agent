// Curated sample texts for the chunking debug drawer. Each preset is sized
// to ≈2000–4000 characters and shaped to exercise a distinct tier of the
// chunker, so users can quickly see how their config behaves on realistic
// content without preparing their own sample.

export interface ChunkingSample {
  id: string
  // i18n key under knowledgeEditor.chunking.debug.samples.<id>
  labelKey: string
  text: string
}

const MARKDOWN_SAMPLE = "# 视觉检测项目设计说明（示例）\n\n本文用于演示文档切分，不代表真实项目或已确认的选型结果。\n\n## 项目目标\n\n设计一台带屏幕的离线视觉检测设备。设备需要采集图像、运行检测算法、显示结果，并保存必要的运行记录。需求梳理时应先明确检测对象、精度、帧率、功耗、环境温度与成本范围。\n\n## 模块与职责\n\n| 模块 | 职责 | 交付物 |\n| --- | --- | --- |\n| 硬件设计 | 接口、电源与板级验证 | 原理图、BOM、测试记录 |\n| 嵌入式软件 | 驱动、通信与设备升级 | 固件及接口说明 |\n| 算法 | 数据整理、模型优化与评估 | 模型与评估报告 |\n| 测试 | 功能与稳定性验证 | 测试用例和缺陷记录 |\n\n### 芯片选型\n\n候选需要核实摄像头输入、显示接口、内存带宽和加速器支持。资料中的典型性能不能直接等同于业务算法实测性能。每项参数应记录来源与资料版本；未明确的参数标记为待核实。\n\n### 接口约定\n\n图像采集模块输出图像及时间戳；算法模块输出目标位置、类别及置信度；显示模块负责结果展示。错误处理需要区分设备离线、输入异常与模型加载失败。\n\n## 验证计划\n\n1. 使用代表性样本完成单次推理验证。\n2. 测量连续运行时的延迟、功耗和温度。\n3. 检查断电恢复、配置保存和升级回退。\n4. 将验证结果与需求逐项关联，记录未解决事项。\n\n## 变更与来源\n\n每次变更记录提出人、日期、影响范围和确认状态。负责人分工以明确确认的记录为准，会议出席名单不作为职责分配依据。\n"

const FAQ_SAMPLE = "# 项目知识管理 FAQ（示例）\n\n## 上传文档后何时可查询？\n\n文档需要完成解析与索引。可在知识库列表查看处理状态；失败时先检查文件内容和配置，再重试。\n\n## 如何查询项目使用的芯片？\n\n描述项目及需要核实的模块，指定相关知识库。查看回答中的来源，确认文档日期、芯片型号与版本。\n\n## 文档有冲突怎么办？\n\n保留每份原始资料的版本和时间。回答应指出冲突，待负责人确认后再更新记录，不应将推测当成事实。\n\n## Wiki 是否替代原始文档？\n\nWiki 用于组织跨文档知识，原文用于核实细节。对关键结论应同时检查来源与更新日期。\n\n## 谁负责一个模块？\n\n依据明确的职责记录或已确认的项目文档。仅参加会议或提交过代码，不自动等于模块负责人。\n\n## 如何维护知识？\n\n上传最新资料，标明版本与有效时间，必要时撤回过期资料。修改后检查索引及 Wiki 的更新状态。\n"

const CHAPTER_SAMPLE = `第 1 章 引言

1.1 文档目的

本文档描述某分布式知识检索平台的整体架构、组件划分与部署方案，面向运维工程师、SRE 与系统架构师。读者应熟悉 Docker、Kubernetes、PostgreSQL 等基础组件。

1.2 名词约定

- 网关层（Gateway）：负责入口流量调度与协议转换
- 业务层（Service）：承载领域逻辑与编排
- 存储层（Storage）：封装持久化与缓存细节
- 推理层（Inference）：与外部 LLM / 嵌入模型交互的隔离层

1.3 文档版本

本版本 v1.4，对应平台代码 v0.5.x 系列。文档随代码同步更新，主要变更见附录 A。

第 2 章 系统架构

2.1 总体设计

平台采用经典的微服务架构，但在边界划分上保持克制——只在确有独立伸缩需求的位置切分服务。当前共 4 个长驻服务：网关、业务后端、文档解析、向量索引。

2.2 模块划分

2.2.1 用户与权限

用户、组织、共享空间、角色与权限规则集中在 user-service 中。RBAC 模型支持继承与覆盖，外部 OIDC 接入通过适配层完成。

2.2.2 内容与索引

内容侧负责文档生命周期：上传、解析、分块、嵌入、入库、检索、引用追踪。Chunk 是最细粒度的检索单元，每个 chunk 携带源文档元数据与位置信息。

2.2.3 推理与编排

Agent 编排器负责 ReAct 循环，工具调用通过 MCP 协议或内置注册表分发。所有 LLM 调用统一经过模型代理层，方便切换、限流与计费。

2.3 数据流

文档上传后依次经过：解析 → 清洗 → 分块 → 嵌入 → 写库。查询路径：rewrite → 多路召回 → fusion → rerank → context 拼接 → LLM 生成。

第 3 章 部署指南

3.1 环境要求

物理资源：8 vCPU / 16 GB 内存 / 100 GB SSD 起步；生产环境建议 16 vCPU / 32 GB / 500 GB。GPU 仅在本地推理时必需。

3.2 容器编排

3.2.1 单机 Docker Compose

适合 PoC 与中小团队（< 100 人，< 100 万 chunk）。一条命令拉起全部服务：

docker compose up -d

3.2.2 Kubernetes Helm

适合规模化部署。Helm chart 在 helm/ 目录，包含 statefulset、配置 secret、ingress 模版。可与现有 PG / Redis 集群对接。

3.3 配置最佳实践

- 把外部依赖（数据库、对象存储、向量库）放在配置中心，避免硬编码
- 模型 API key 用 Secret 管理，按环境隔离
- 日志走 stdout/stderr 由编排平台采集，避免本地落盘

第 4 章 常见运维场景

4.1 升级流程

蓝绿或滚动均可。升级前必看 CHANGELOG 中是否有 schema 变更，迁移先于业务镜像替换。

4.2 备份与恢复

PG 全量每日备份 + WAL 增量；MinIO/对象存储依赖云端版本管理。Qdrant 用 snapshot 接口定期落盘到对象存储。

4.3 故障排查

按"网关 → 业务 → 存储 → 模型"四个维度逐层排查。每层都有健康检查接口与 Langfuse trace 入口，组合起来可在 5 分钟内定位 80% 问题。`

const PLAIN_SAMPLE = `知识库的检索质量受多个因素影响，最直接的是切分策略与嵌入模型的匹配度。切分过粗会导致单段语义混杂、相关度被稀释；切分过细则丢失上下文，单独检索某一段无法回答跨段问题。一般建议切分大小落在嵌入模型推荐窗口的 50%–80%，既保证语义完整又留出余量。常见嵌入模型如 BGE、Cohere 的 embed-v3 推荐窗口为 512 tokens，对应字符大致在 300–800 之间，因为中文一个字约 0.5–1.2 个 token，英文一个词约 1.3 个 token。

除了切分大小，重叠（overlap）也会显著影响召回完整性。重叠为 0 时，跨段问题往往只能召回半句话；重叠 10%–20% 通常就足够覆盖大多数边界情况；重叠超过 30% 会让相邻分块大量同质化，反而增加索引成本而不提升召回。一个简单的判断方法：对你的目标查询，平均答案长度的 1/3 作为 overlap 起点，再根据 A/B 测试微调。

分隔符的选择应贴合文档真实结构。纯文本可保留默认双换行作为强分隔；Markdown 文档建议保留标题层级，先按标题切，再在大标题内部按段落切；代码与表格混合的内容则需要更精细的策略，例如 Tree-sitter 抽取代码结构、识别表格边界，或者直接用脚本把这两类内容预先分离再走文本切分。如果文档里大量混合中英文，分隔符里务必同时包含中文标点（。！？）和英文标点（. ! ?），否则只对一种语言生效，效果会很差。

嵌入模型的选择往往被低估。开源里 BGE-large 系列在中文 benchmark 上稳定领先，BGE-M3 同时支持稠密、稀疏、ColBERT 多向量；商用 OpenAI text-embedding-3-large 通用性强、成本不算高，Voyage-3-large 在英文上略胜一筹但中文一般。对长文档场景，注意嵌入模型的最大输入长度——OpenAI 是 8191 tokens，BGE 默认 512，超长输入会被截断或分段嵌入再平均，效果都不好。

最后，别忽视后处理。重排（rerank）几乎在所有场景都能提升 5%–15% 的端到端效果，代价是每次查询多 100–300ms 延迟。常见 reranker 包括 BGE-Reranker、Cohere Rerank，前者开源、后者付费但效果略好。如果你的检索路径包含关键词召回，强烈建议用 reranker 做第二层过滤，不然 BM25 的纯字面命中会污染上下文。`

export const CHUNKING_SAMPLES: ChunkingSample[] = [
  { id: "markdown", labelKey: "samples.markdown", text: MARKDOWN_SAMPLE },
  { id: "faq", labelKey: "samples.faq", text: FAQ_SAMPLE },
  { id: "chapter", labelKey: "samples.chapter", text: CHAPTER_SAMPLE },
  { id: "plain", labelKey: "samples.plain", text: PLAIN_SAMPLE },
];

export const DEFAULT_SAMPLE_ID = "markdown";
