<template>
  <main class="workspace-onboarding">
    <section class="workspace-card">
      <img src="@/assets/solex/solex-wordmark.svg" alt="SOLEX" class="workspace-brand" />
      <div class="workspace-mark" aria-hidden="true">
        <t-icon name="usergroup" size="28px" />
      </div>
      <h1 v-if="authStore.canCreateTenant">{{ $t('auth.workspaceOnboarding.title') }}</h1>
      <h1 v-else>{{ $t('auth.workspaceOnboarding.inviteOnlyTitle') }}</h1>
      <p v-if="authStore.canCreateTenant" class="workspace-description">
        {{ $t('auth.workspaceOnboarding.description') }}
      </p>
      <p v-else class="workspace-description">
        {{ $t('auth.workspaceOnboarding.inviteOnlyDescription') }}
      </p>

      <div v-if="policyLoading" class="policy-loading">
        <t-loading size="small" />
        <span>{{ $t('auth.workspaceOnboarding.loadingPolicy') }}</span>
      </div>
      <div v-else-if="policyLoadFailed" class="policy-error" role="alert">
        <t-icon name="error-circle" size="20px" aria-hidden="true" />
        <span>{{ $t('auth.workspaceOnboarding.policyLoadFailed') }}</span>
        <t-button size="small" variant="text" @click="loadPolicy">
          {{ $t('auth.workspaceOnboarding.retry') }}
        </t-button>
      </div>

      <template v-else>
        <div v-if="!authStore.canCreateTenant" class="invite-only-notice">
          <t-icon name="lock-on" size="20px" aria-hidden="true" />
          <span>{{ $t('auth.workspaceOnboarding.inviteOnlyNotice') }}</span>
        </div>

        <div class="workspace-actions" :class="{ 'workspace-actions--single': !authStore.canCreateTenant }">
          <t-button v-if="authStore.canCreateTenant" theme="primary" size="large" @click="createVisible = true">
            <template #icon><t-icon name="add" /></template>
            {{ $t('auth.workspaceOnboarding.create') }}
          </t-button>
          <t-button
            :theme="authStore.canCreateTenant ? 'default' : 'primary'"
            :variant="authStore.canCreateTenant ? 'outline' : 'base'"
            size="large"
            @click="invitationsVisible = true"
          >
            <template #icon><t-icon name="mail" /></template>
            {{ $t('auth.workspaceOnboarding.invitations') }}
            <template v-if="authStore.pendingInvitationCount > 0">
              ({{ authStore.pendingInvitationCount }})
            </template>
          </t-button>
        </div>
      </template>

      <p v-if="!policyLoading && !policyLoadFailed && authStore.canCreateTenant" class="workspace-help">
        {{ $t('auth.workspaceOnboarding.help') }}
      </p>
      <p v-else-if="!policyLoading && !policyLoadFailed" class="workspace-help">
        {{ $t('auth.workspaceOnboarding.inviteOnlyHelp') }}
      </p>
      <button class="logout-link" type="button" @click="handleLogout">
        {{ $t('auth.logout') }}
      </button>
    </section>

    <CreateTenantDialog v-model:visible="createVisible" @created="onTenantCreated" />
    <MyInvitationsDialog v-model:visible="invitationsVisible" />
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import CreateTenantDialog from '@/components/CreateTenantDialog.vue'
import MyInvitationsDialog from '@/components/MyInvitationsDialog.vue'
import { logout as logoutApi } from '@/api/auth'
import type { TenantInfo } from '@/api/tenant'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const createVisible = ref(false)
const invitationsVisible = ref(false)
const policyLoading = ref(true)
const policyLoadFailed = ref(false)

async function loadPolicy() {
  policyLoading.value = true
  policyLoadFailed.value = false
  try {
    const refreshed = await authStore.refreshFromAuthMe()
    if (!refreshed) {
      policyLoadFailed.value = true
      return
    }
    await authStore.fetchPendingInvitationCount()
  } finally {
    policyLoading.value = false
  }
}

onMounted(async () => {
  await loadPolicy()
})

watch(
  () => authStore.hasValidTenant,
  (ready) => {
    if (ready) router.replace('/platform/knowledge-bases')
  },
)

async function onTenantCreated(tenant: TenantInfo) {
  await authStore.refreshFromAuthMe()
  authStore.setSelectedTenant(tenant.id, tenant.name)
  await router.replace('/platform/knowledge-bases')
}

async function handleLogout() {
  await logoutApi()
  authStore.logout()
  await router.replace('/login')
}
</script>

<style scoped lang="less">
.workspace-onboarding {
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background: #f5f8f8;
  box-sizing: border-box;
}

.workspace-card {
  width: min(540px, 100%);
  box-sizing: border-box;
  padding: 44px;
  border: 1px solid #dce7e7;
  border-radius: var(--solex-radius-card);
  background: #fff;
  box-shadow: 0 22px 60px -24px #234b5620;
  text-align: center;
}

.workspace-brand { display: block; width: 118px; height: 30px; margin: 0 auto 34px; }
.workspace-mark {
  width: 56px;
  height: 56px;
  margin: 0 auto 22px;
  display: grid;
  place-items: center;
  border-radius: var(--solex-radius-panel);
  border: 1px solid #deeeee;
  color: #087f8c;
  background: #edf7f7;
}

h1 { margin: 0; color: #172d35; font-size: var(--solex-text-heading); font-weight: 600; line-height: 1.4; letter-spacing: -.025em; }
.workspace-description, .workspace-help { color: #7a8d93; line-height: 1.8; }
.workspace-description { margin: 14px 0 28px; font-size: var(--app-text-md); }
.workspace-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.workspace-actions--single { grid-template-columns: minmax(0, 1fr); }
.workspace-actions :deep(.t-button) { border-radius: var(--app-radius-md); min-height: 46px; font-size: var(--app-text-md); }
.workspace-actions :deep(.t-button--theme-primary) { background: #087f8c; border-color: #087f8c; }
.workspace-actions :deep(.t-button--theme-primary:hover) { background: #076c78; border-color: #076c78; }

.policy-loading, .invite-only-notice, .policy-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 52px;
  margin-bottom: 18px;
  color: #6d8086;
  font-size: var(--app-text-sm);
}
.policy-error { flex-wrap: wrap; padding: 12px 16px; border: 1px solid #f1d9d9; border-radius: var(--app-radius-lg); color: #b04444; background: #fff7f7; }
.invite-only-notice { padding: 14px 16px; border: 1px solid #dceced; border-radius: var(--app-radius-lg); color: #526d74; background: #f2f9f9; line-height: 1.7; text-align: left; }
.invite-only-notice :deep(.t-icon) { flex: 0 0 auto; color: #087f8c; }
.workspace-help { margin: 24px 0 8px; font-size: var(--app-text-sm); }
.logout-link { border: 0; border-radius: var(--app-radius-xs); padding: 7px 10px; font-size: var(--app-text-sm); color: #718b92; background: transparent; cursor: pointer; }
.logout-link:hover { color: #087f8c; background: #f2f8f8; }
.logout-link:focus-visible { outline: 2px solid #087f8c; outline-offset: 2px; }

@media (max-width: 560px) {
  .workspace-card { padding: 32px 24px; }
  .workspace-actions { grid-template-columns: 1fr; }
  h1 { font-size: var(--solex-text-title); }
}
</style>
