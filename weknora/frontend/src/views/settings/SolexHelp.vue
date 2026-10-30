<template>
  <div class="solex-help">
    <header class="help-header">
      <span class="help-eyebrow">SOLEX / HELP</span>
      <h2>{{ chinese ? '从问题出发，让知识参与工作。' : 'Turn your questions into informed work.' }}</h2>
      <p>{{ chinese ? '了解如何开展调研、管理企业资料，以及连接你的工作工具。' : 'Research ideas, organize company knowledge, and connect your working tools.' }}</p>
    </header>
    <nav class="help-topics" :aria-label="chinese ? '帮助主题' : 'Help topics'">
      <button v-for="item in topics" :key="item.key" type="button"
        :class="['help-topic', { active: item.key === selected.key }]"
        :aria-pressed="item.key === selected.key" @click="selectTopic(item.key)">
        <t-icon :name="item.icon" size="18px" />
        <span>{{ item.title }}</span>
      </button>
    </nav>
    <article class="help-article" aria-live="polite">
      <div class="help-article-heading"><t-icon :name="selected.icon" size="22px" /><h3>{{ selected.title }}</h3></div>
      <p class="help-intro">{{ selected.intro }}</p>
      <ol class="help-steps">
        <li v-for="(step, index) in selected.steps" :key="step">
          <span class="help-step-number">{{ String(index + 1).padStart(2, '0') }}</span>
          <p>{{ step }}</p>
        </li>
      </ol>
      <div v-if="selected.links?.length" class="help-links">
        <router-link v-for="link in selected.links" :key="link.to" :to="link.to">
          {{ link.label }} <t-icon name="arrow-right" size="16px" />
        </router-link>
      </div>
    </article>
    <p class="help-note">{{ chinese ? '看不到某项入口时，请联系空间管理员确认权限和服务是否已启用。' : 'If an option is unavailable, ask your workspace administrator to check your access and enabled services.' }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { docsUrl, type DocPage } from '@/utils/docsUrl'

interface HelpTopic {
  key: DocPage
  title: string
  icon: string
  intro: string
  steps: string[]
  links?: { label: string; to: string }[]
}

const route = useRoute()
const router = useRouter()
const { locale } = useI18n()
const chinese = computed(() => locale.value.startsWith('zh'))
const settings = (section: string) => `/platform/settings?section=${section}`
const topics = computed<HelpTopic[]>(() => chinese.value ? [
  { key: 'home', title: '开始使用', icon: 'chat-bubble', intro: '用自然语言描述目标、约束和你已经掌握的信息。', steps: [
    '新建对话，选择合适的智能体。调研问题可以从应用场景、性能要求、预算和交付时间开始。',
    '回答助手的追问，也可以随时补充或修正需求。需要初步结论时，明确说明允许采用哪些假设。',
    '查询企业资料时选择相关知识库；查询公开信息时按需启用联网搜索。查看回答中的来源，核实关键参数和版本。',
    '从最近对话继续工作。企业知识是否可见由所在空间和共享设置决定。',
  ] },
  { key: 'tenantAuth', title: '空间与成员', icon: 'usergroup', intro: '在正确的企业空间里协作，按角色使用知识和工具。', steps: [
    '通过企业提供的入口登录。收到邀请时，使用邀请对应的账号加入空间。',
    '切换空间后确认知识库和智能体列表。不同空间的数据与授权可能不同。',
    '管理员可以在成员管理中邀请成员、调整角色或移除成员。修改权限前确认影响范围。',
  ], links: [{ label: '成员管理', to: settings('members') }] },
  { key: 'models', title: '模型连接', icon: 'control-platform', intro: '对话模型负责理解与生成，向量模型负责资料的语义检索。', steps: [
    '管理员在模型管理中填写服务地址、模型标识和凭据，先验证连接再设为默认模型。',
    '知识库建立索引前应选择可用的向量模型。更换向量模型时，确认是否需要重新建立索引。',
    '回答失败时先检查模型是否可用、额度与限流情况，再重试当前问题。不要在聊天中发送 API 密钥。',
  ], links: [{ label: '模型管理', to: settings('models') }, { label: '默认配置', to: settings('defaults') }] },
  { key: 'modelsCompat', title: '模型兼容设置', icon: 'adjustment', intro: '不同模型支持的生成参数和推理能力可能不同。', steps: [
    '优先使用已验证的模型配置。服务地址和模型标识应与提供方给出的接口信息一致。',
    '只有提供方明确要求时才覆盖采样、推理或工具调用参数。不要把某个模型的固定参数直接用于其他模型。',
    '修改后分别验证普通问答与推理问答，确认能收到完整回答，再应用到智能体。',
  ], links: [{ label: '模型管理', to: settings('models') }] },
  { key: 'knowledgeGraph', title: '知识库与 Wiki', icon: 'books', intro: '原始资料保留依据，Wiki 帮助整理项目、模块和相关知识。', steps: [
    '创建或打开知识库，上传项目文档、导入网页或编写内容。等待解析与索引完成后再检索。',
    '在知识库中启用 Wiki 后，检查整理状态与生成页面。资料已上传并不表示 Wiki 已生成完毕。',
    '核对负责人、芯片型号和版本等关键事实。不同资料有冲突时，结合来源时间和正式记录判断。',
    '更新或删除原始资料后，检查索引与 Wiki 是否完成同步，并再次验证相关问题的来源。',
  ] },
  { key: 'imIntegration', title: '消息工具接入', icon: 'chat-message', intro: '将已配置的智能体连接到团队正在使用的消息工具。', steps: [
    '由管理员在消息集成中选择支持的平台，并按页面提示填写应用或机器人凭据。',
    '确认关联空间、智能体与允许访问的知识范围，再完成平台侧的回调或连接配置。',
    '使用一条不含内部敏感信息的测试消息验证收发。团队成员使用前，确认平台侧权限。',
  ], links: [{ label: '消息集成', to: settings('integration-im') }] },
  { key: 'apiOverview', title: 'API 与客户端', icon: 'code', intro: '通过 API、MCP、命令行或企业批准的客户端使用现有知识能力。', steps: [
    '从 API 集成页复制当前服务地址。由空间所有者配置访问凭据及权限，不要把凭据放进公开代码。',
    'MCP 客户端可使用页面生成的连接配置；命令行和浏览器扩展使用企业管理员提供的安装包或客户端。',
    '第三方技能所需的变量名与鉴权字段应遵循实际客户端协议。先用独立测试资料验证连接，再访问业务资料。',
    '接入失败时检查服务地址、凭据有效期、访问范围与网络连接。撤销不用的密钥，并更新对应客户端。',
  ], links: [{ label: 'API 集成', to: settings('integration-api') }, { label: 'MCP 服务', to: settings('integration-mcpserver') }] },
  { key: 'sandboxDeployment', title: '工具运行环境', icon: 'code', intro: '需要执行技能或处理文件的智能体，可使用管理员启用的运行环境。', steps: [
    '管理员先配置并验证可用的运行环境，再为智能体选择需要的工具或技能。',
    '工具需要个人凭据时，在沙箱密钥设置中保存。只授予完成当前工作所需的访问权限。',
    '执行过程中关注工具请求与结果。失败时查看任务提示，确认资源和依赖可用后再重试。',
  ], links: [{ label: '运行环境', to: settings('sandbox') }, { label: '个人密钥', to: settings('envvars') }] },
  { key: 'troubleshootingMigrations', title: '遇到问题', icon: 'help-circle', intro: '保留问题发生的时间、操作步骤和页面提示，便于企业管理员定位。', steps: [
    '页面无法正常加载时先刷新并重新登录；确认网络连接正常，且使用的是企业提供的入口。',
    '模型回答或文档处理失败时，记录对应对话或资料名称。不要反复提交同一批文件。',
    '系统提示数据库升级或服务异常时，联系管理员处理。不要自行删除资料或修改数据库。',
    '管理员可在版本信息与任务队列中查看状态。反馈时不要附带密码、API 密钥或完整内部文档。',
  ], links: [{ label: '版本信息', to: settings('system') }] },
] : [
  { key: 'home', title: 'Get started', icon: 'chat-bubble', intro: 'Describe your goal, constraints, and what you already know.', steps: ['Start a chat and choose an agent suited to your work.', 'Answer follow-up questions and revise your requirements whenever needed.', 'Select knowledge bases for internal questions and enable web search for public research. Check sources, dates, and versions.', 'Continue work from recent chats. Knowledge visibility depends on your workspace and sharing settings.'] },
  { key: 'tenantAuth', title: 'Workspaces and members', icon: 'usergroup', intro: 'Collaborate in the right workspace with appropriate access.', steps: ['Sign in through your company entry point and accept invitations with the intended account.', 'Check the current workspace before selecting knowledge bases and agents.', 'Administrators can invite members and adjust their roles.'], links: [{ label: 'Manage members', to: settings('members') }] },
  { key: 'models', title: 'Connect models', icon: 'control-platform', intro: 'Chat models generate answers; embedding models support semantic retrieval.', steps: ['An administrator adds the service URL, model ID, and credentials, then tests the connection.', 'Choose a working embedding model before indexing documents. A model change may require reindexing.', 'Check model availability, quotas, and rate limits when a request fails. Never paste API keys into chat.'], links: [{ label: 'Models', to: settings('models') }] },
  { key: 'modelsCompat', title: 'Model compatibility', icon: 'adjustment', intro: 'Generation and reasoning options vary between models.', steps: ['Use a verified model configuration and the exact endpoint and model ID supplied by your provider.', 'Override sampling or reasoning options only when the provider requires it.', 'Test both ordinary and reasoning conversations after changing the configuration.'], links: [{ label: 'Models', to: settings('models') }] },
  { key: 'knowledgeGraph', title: 'Knowledge and Wiki', icon: 'books', intro: 'Keep original evidence while organizing related project knowledge.', steps: ['Upload documents, import pages, or write content, then wait for parsing and indexing.', 'Enable Wiki in the knowledge base and inspect generation status separately from document upload status.', 'Verify owners, chip models, versions, and conflicting claims against original sources.', 'After updating or removing a source, check synchronization and repeat a relevant query.'] },
  { key: 'imIntegration', title: 'Messaging tools', icon: 'chat-message', intro: 'Connect an existing agent to your team messaging platform.', steps: ['An administrator configures a supported platform and its application credentials.', 'Check the linked workspace, agent, and permitted knowledge before enabling callbacks.', 'Test delivery with a non-sensitive message and verify platform permissions.'], links: [{ label: 'Messaging integration', to: settings('integration-im') }] },
  { key: 'apiOverview', title: 'API and clients', icon: 'code', intro: 'Use APIs, MCP, command-line tools, or company-approved clients.', steps: ['Copy the current API address from integration settings. A workspace owner controls credentials and access.', 'Use the generated MCP configuration. Ask your administrator for approved command-line tools and browser extensions.', 'Keep the variable names and authentication fields required by the actual client protocol. Test with separate sample content first.', 'Check endpoints, credential validity, scope, and connectivity when a connection fails. Revoke unused credentials.'], links: [{ label: 'API integration', to: settings('integration-api') }, { label: 'MCP service', to: settings('integration-mcpserver') }] },
  { key: 'sandboxDeployment', title: 'Tool environments', icon: 'code', intro: 'Agents can run skills and process files in an administrator-enabled environment.', steps: ['An administrator configures and verifies the runtime before enabling relevant tools.', 'Store personal tool credentials in secret settings and grant only the access the task requires.', 'Review tool requests and results. Check the failure message and available resources before retrying.'], links: [{ label: 'Tool environments', to: settings('sandbox') }] },
  { key: 'troubleshootingMigrations', title: 'Troubleshooting', icon: 'help-circle', intro: 'Record the time, steps, and visible message so your administrator can help.', steps: ['Refresh and sign in again if a page fails to load. Check connectivity and your company entry point.', 'Record the affected chat or document when processing fails. Avoid repeatedly uploading the same batch.', 'Contact your administrator for database upgrade or service errors. Do not delete business data to resolve them.', 'Administrators can inspect version information and queues. Do not include passwords, keys, or full internal documents in feedback.'], links: [{ label: 'Version information', to: settings('system') }] },
])
const selected = computed(() => topics.value.find((item) => item.key === route.query.topic) ?? topics.value[0]!)
const selectTopic = (key: DocPage) => router.replace(docsUrl(key))
</script>

<style scoped lang="less">
.solex-help { max-width: 980px; margin: 0 auto; padding: 6px 0 24px; color: var(--td-text-color-primary); }
.help-header { padding: 24px; border: 1px solid var(--td-component-stroke); border-radius: var(--app-radius-xl); background: linear-gradient(125deg, var(--td-bg-color-container), var(--td-brand-color-light)); }
.help-eyebrow { color: var(--td-brand-color); font-size: var(--app-text-xs); letter-spacing: .18em; font-weight: 700; }
.help-header h2 { margin: 16px 0 10px; font-size: var(--app-text-4xl); line-height: 1.4; letter-spacing: -.025em; color: var(--td-text-color-primary); }
.help-header p, .help-intro { margin: 0; line-height: 1.75; color: var(--td-text-color-secondary); }
.help-topics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; margin: 20px 0; }
.help-topic { display: flex; align-items: center; gap: 9px; min-height: 48px; padding: 10px 12px; border: 1px solid var(--td-component-stroke); border-radius: var(--app-radius-xl); background: var(--td-bg-color-container); color: var(--td-text-color-secondary); font: inherit; text-align: left; cursor: pointer; transition: border-color var(--app-motion-fast), background var(--app-motion-fast); }
.help-topic:hover, .help-topic.active { border-color: color-mix(in srgb, var(--td-brand-color) 40%, var(--td-component-stroke)); background: var(--td-brand-color-light); color: var(--td-brand-color); }
.help-topic:focus-visible { outline: 2px solid var(--td-brand-color); outline-offset: 2px; }
.help-article { padding: 24px; border: 1px solid var(--td-component-stroke); border-radius: var(--app-radius-xl); background: var(--td-bg-color-container); }
.help-article-heading { display: flex; align-items: center; gap: 10px; color: var(--td-brand-color); }
.help-article h3 { margin: 0 0 1px; font-size: var(--app-text-2xl); color: var(--td-text-color-primary); }
.help-intro { margin-top: 12px; }
.help-steps { list-style: none; padding: 0; margin: 20px 0 0; }
.help-steps li { display: flex; align-items: flex-start; gap: 14px; padding: 14px 0; border-top: 1px solid var(--td-component-stroke); }
.help-step-number { flex-shrink: 0; font-size: var(--app-text-sm); line-height: 1.9; font-weight: 700; color: var(--td-brand-color); }
.help-steps p { margin: 0; line-height: 1.8; font-size: var(--app-text-md); }
.help-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.help-links a { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--td-component-border); border-radius: var(--app-radius-lg); color: var(--td-brand-color); text-decoration: none; padding: 8px 12px; }
.help-links a:hover { background: var(--td-brand-color-light); }
.help-note { margin: 16px 2px 0; color: var(--td-text-color-placeholder); font-size: var(--app-text-sm); line-height: 1.7; }
@media (max-width: 650px) { .help-topics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .help-header, .help-article { padding: 18px; } .help-header h2 { font-size: var(--app-text-3xl); } }
</style>
