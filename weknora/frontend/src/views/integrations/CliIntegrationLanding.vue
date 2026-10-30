<template>
  <IntegrationLandingLayout
    :title="$t('integrations.cli.title')"
    :subtitle="$t('integrations.cli.subtitle')"
    variant="cli"
  >
    <template #actions>
      <IntegrationExternalCta
        :label="$t('integrations.cli.docs')"
        :hint="chinese ? '服务连接与客户端使用说明' : 'Service and client connection guide'"
        @click="openDocs"
      >
        <template #icon><t-icon name="code" /></template>
      </IntegrationExternalCta>
    </template>

    <template #main>
      <div class="landing-group">
        <section class="setting-drawer__section">
          <h4 class="setting-drawer__section-title">{{ $t('integrations.cli.quickstart') }}</h4>
          <ol class="landing-steps">
            <li v-for="(step, index) in steps" :key="step.key" class="landing-step">
              <span class="landing-step-num">{{ index + 1 }}</span>
              <div class="landing-step-body">
                <div class="landing-step-title">{{ $t(`integrations.cli.${step.key}Title`) }}</div>
                <p class="landing-step-desc">{{ step.key === 'install' ? (chinese ? '向企业管理员获取兼容的命令行客户端，将下方路径替换为本机可执行文件的绝对路径。' : 'Ask your administrator for a compatible command-line client, then replace the path below with the absolute path to its executable.') : $t(`integrations.cli.${step.key}Desc`) }}</p>
                <div class="landing-step-embed code-toolbar">
                  <pre class="code-toolbar__code">{{ step.command }}</pre>
                  <t-button
                    class="code-toolbar__copy"
                    size="small"
                    variant="text"
                    shape="square"
                    :title="$t('integrations.cli.copy')"
                    :aria-label="$t('integrations.cli.copy')"
                    @click="copy(step.command)"
                  >
                    <t-icon name="file-copy" size="16px" />
                  </t-button>
                </div>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </template>

    <template #aside>
      <div class="landing-group">
        <section v-for="example in examples" :key="example.key" class="setting-drawer__section">
          <h4 class="setting-drawer__section-title">{{ $t(`integrations.cli.${example.key}Title`) }}</h4>
          <p class="field-desc">{{ $t(`integrations.cli.${example.key}Desc`) }}</p>
          <div class="code-toolbar">
            <pre class="code-toolbar__code">{{ example.command }}</pre>
            <t-button
              class="code-toolbar__copy"
              size="small"
              variant="text"
              shape="square"
              :title="$t('integrations.cli.copy')"
              :aria-label="$t('integrations.cli.copy')"
              @click="copy(example.command)"
            >
              <t-icon name="file-copy" size="16px" />
            </t-button>
          </div>
        </section>
      </div>
    </template>
  </IntegrationLandingLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { docsUrl } from '@/utils/docsUrl'
import { useApiBaseUrlDisplay } from '@/composables/useApiBaseUrlDisplay'
import { copyWithToast } from '@/utils/clipboard'
import IntegrationLandingLayout from './IntegrationLandingLayout.vue'
import IntegrationExternalCta from './IntegrationExternalCta.vue'
import { buildCLIConnectCommand } from './cliIntegration'

const { apiBaseUrlDisplay } = useApiBaseUrlDisplay()
const router = useRouter()
const { locale } = useI18n()
const chinese = computed(() => locale.value.startsWith('zh'))
const steps = computed(() => [
  {
    key: 'install',
    command: 'export CLI_BIN="/absolute/path/to/your-cli"\n"$CLI_BIN" --help',
  },
  { key: 'connect', command: buildCLIConnectCommand(apiBaseUrlDisplay.value, window.location.origin, true) },
  { key: 'verify', command: '"$CLI_BIN" doctor\n"$CLI_BIN" kb list' },
])
const examples = [
  {
    key: 'commands',
    command: '"$CLI_BIN" doc upload ./document.pdf --kb "KB_ID"\n"$CLI_BIN" search chunks "query" --kb "KB_ID"\n"$CLI_BIN" chat "question" --kb "KB_ID" --format text\n"$CLI_BIN" agent list',
  },
  {
    key: 'mcp',
    command: JSON.stringify({
      mcpServers: {
        solex: { command: '/absolute/path/to/your-cli', args: ['--profile', 'solex', 'mcp', 'serve'] },
      },
    }, null, 2),
  },
]

const copy = (command: string) => copyWithToast(command, 'integrations.cli.copied')
const openDocs = () => router.push(docsUrl('apiOverview'))
</script>
