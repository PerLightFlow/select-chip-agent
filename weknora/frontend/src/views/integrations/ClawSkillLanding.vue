<template>
  <IntegrationLandingLayout
    :title="$t('integrations.claw.title')"
    :subtitle="$t('integrations.claw.subtitle')"
    variant="claw"
  >
    <template #actions>
      <IntegrationExternalCta
        variant="claw"
        :label="chinese ? '接入说明' : 'Connection guide'"
        :hint="chinese ? '连接企业批准的技能包' : 'Connect an approved skill package'"
        @click="openHelp"
      >
        <template #icon>
          <t-icon name="tools" size="18px" />
        </template>
      </IntegrationExternalCta>
    </template>

    <template #main>
      <div class="landing-group">
        <section class="setting-drawer__section">
          <h4 class="setting-drawer__section-title">
            {{ $t('integrations.claw.capabilitiesTitle') }}
            <span class="section-head-extra">{{ capabilityKeys.length }}</span>
          </h4>
          <div class="capability-grid capability-grid--claw">
            <div v-for="key in capabilityKeys" :key="key" class="capability-card">
              <div class="capability-card__icon">
                <t-icon :name="capabilityIcons[key]" />
              </div>
              <h5 class="capability-card__title">{{ $t(`integrations.claw.capabilities.${key}.title`) }}</h5>
              <p class="capability-card__desc">{{ $t(`integrations.claw.capabilities.${key}.desc`) }}</p>
            </div>
          </div>
        </section>
      </div>
    </template>

    <template #aside>
      <div class="landing-group">
        <section class="setting-drawer__section">
          <h4 class="setting-drawer__section-title">{{ $t('integrations.claw.stepsTitle') }}</h4>
          <ol class="landing-steps">
            <li v-for="(step, index) in stepKeys" :key="step" class="landing-step">
              <span class="landing-step-num">{{ index + 1 }}</span>
              <div class="landing-step-body">
                <div class="landing-step-title">{{ step === 'install' ? (chinese ? '获取技能包' : 'Get the skill') : $t(`integrations.claw.steps.${step}.title`) }}</div>
                <p class="landing-step-desc">{{ step === 'install' ? (chinese ? '向企业管理员获取已批准的技能包，并按客户端说明导入；连接前确认资料访问范围。' : 'Ask your administrator for an approved skill package and import it using your client. Check the data access scope before connecting.') : $t(`integrations.claw.steps.${step}.desc`) }}</p>
                <t-button
                  v-if="step === 'api'"
                  size="small"
                  variant="outline"
                  class="landing-step-action"
                  @click="openApiSettings"
                >
                  {{ $t('integrations.claw.openApiSettings') }}
                </t-button>
                <div v-if="step === 'env'" class="landing-step-embed">
                  <div class="code-toolbar">
                    <pre class="code-toolbar__code">{{ envExample }}</pre>
                    <t-button
                      class="code-toolbar__copy"
                      size="small"
                      variant="text"
                      shape="square"
                      :title="$t('integrations.claw.copy')"
                      @click="copyEnvExample"
                    >
                      <t-icon name="file-copy" size="16px" />
                    </t-button>
                  </div>
                </div>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </template>

  </IntegrationLandingLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { copyWithToast } from '@/utils/clipboard'
import { useRouter } from 'vue-router'
import { docsUrl } from '@/utils/docsUrl'
import { useApiBaseUrlDisplay } from '@/composables/useApiBaseUrlDisplay'
import { useUIStore } from '@/stores/ui'
import IntegrationLandingLayout from './IntegrationLandingLayout.vue'
import IntegrationExternalCta from './IntegrationExternalCta.vue'

const router = useRouter()
const { locale } = useI18n()
const chinese = computed(() => locale.value.startsWith('zh'))
const uiStore = useUIStore()
const { apiBaseUrlDisplay } = useApiBaseUrlDisplay()

const capabilityKeys = ['upload', 'url', 'manual', 'search', 'browse'] as const
const stepKeys = ['api', 'env', 'install', 'verify'] as const

const capabilityIcons: Record<(typeof capabilityKeys)[number], string> = {
  upload: 'upload',
  url: 'link',
  manual: 'edit',
  search: 'search',
  browse: 'view-list',
}

const envExample = computed(() => {
  const base = apiBaseUrlDisplay.value || 'https://your-server.com/api/v1'
  return `export WEKNORA_BASE_URL="${base}"\nexport WEKNORA_API_KEY="sk-your-api-key"`
})

const openHelp = () => router.push(docsUrl('apiOverview'))

const openApiSettings = () => {
  router.push({ path: '/platform/settings', query: { section: 'integration-api' } })
  uiStore.openSettings('integration-api')
}

const copyEnvExample = () => copyWithToast(envExample.value, 'integrations.claw.copyEnvSuccess')
</script>
