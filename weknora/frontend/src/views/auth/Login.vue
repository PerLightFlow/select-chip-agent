<template>
  <div class="login-layout">
    <header class="login-header">
      <div class="header-logo" aria-label="SOLEX">
        <img src="@/assets/solex/solex-wordmark.svg" alt="SOLEX" class="logo-image" />
        <span class="brand-divider" aria-hidden="true"></span>
        <span class="brand-caption">智能知识工作台</span>
      </div>
      <div class="language-switch" @keydown.esc="showLanguageMenu = false">
        <button type="button" @click="toggleLanguageMenu" class="language-trigger"
          :title="currentLangOption?.label" :aria-label="currentLangOption?.label"
          :aria-expanded="showLanguageMenu" aria-haspopup="menu">
          <t-icon name="translate" size="18px" />
          <span>{{ currentLangOption?.shortLabel }}</span>
          <t-icon name="chevron-down" size="14px" />
        </button>
        <div v-if="showLanguageMenu" class="language-dropdown" role="menu">
          <button v-for="lang in languageOptions" :key="lang.value" type="button"
            @click="selectLanguage(lang.value)" class="language-option"
            :class="{ active: currentLanguage === lang.value }" role="menuitemradio"
            :aria-checked="currentLanguage === lang.value">
            <span>{{ lang.label }}</span>
            <t-icon v-if="currentLanguage === lang.value" name="check" size="16px" />
          </button>
        </div>
      </div>
    </header>

    <main class="login-main">
      <section class="showcase-section" aria-labelledby="showcase-title">
        <div class="showcase-eyebrow"><span></span>连接知识 · 激发洞见</div>
        <h1 id="showcase-title">让知识，<br />成为下一步<span class="headline-accent">行动。</span></h1>
        <p class="showcase-description">汇集团队经验，探索问题的答案。<br />从一份资料、一个想法，走向清晰的判断。</p>

        <div class="knowledge-map" aria-label="项目资料与团队经验汇入企业知识，支持检索、调研和来源追溯">
          <div class="map-heading"><span>从分散的信息，到连接的知识</span><span class="map-caption">SOLEX / KNOWLEDGE</span></div>
          <div class="map-canvas">
            <svg class="map-connections" viewBox="0 0 500 220" preserveAspectRatio="none" aria-hidden="true">
              <path d="M88 54 V94 Q88 110 104 110 H234" />
              <path d="M250 54 V91" />
              <path d="M412 54 V94 Q412 110 396 110 H266" />
              <path class="map-connection-active" d="M250 133 V174" />
              <circle cx="88" cy="54" r="3" /><circle cx="412" cy="54" r="3" />
              <circle cx="250" cy="174" r="3" />
            </svg>
            <div class="source-nodes">
              <div class="source-node"><t-icon name="file-copy" size="19px" /><span>项目资料</span></div>
              <div class="source-node"><t-icon name="usergroup" size="19px" /><span>团队经验</span></div>
              <div class="source-node"><t-icon name="internet" size="19px" /><span>行业信息</span></div>
            </div>
            <div class="knowledge-hub"><img src="@/assets/solex/solex-symbol.svg" alt="" /><span>企业知识</span><span class="hub-dot" aria-hidden="true"></span></div>
            <div class="knowledge-outcome"><t-icon name="chat-bubble" size="17px" /><span>让每一次探索，都有迹可循</span><t-icon name="arrow-right" size="16px" /></div>
          </div>
          <div class="map-footer"><span><t-icon name="check" size="14px" /> 梳理需求</span><span><t-icon name="check" size="14px" /> 连接信息</span><span><t-icon name="check" size="14px" /> 追溯来源</span></div>
        </div>
        <p class="showcase-note">企业知识与智能探索，在同一个工作空间。</p>
      </section>

      <section class="form-section" aria-label="账号访问">
        <div class="form-panel">
          <div class="form-card" v-if="!isRegisterMode">
            <div class="form-heading-mark"><t-icon name="login" size="22px" /></div>
            <div class="form-header">
              <p class="form-eyebrow">欢迎来到 SOLEX</p>
              <h2 class="form-title">{{ $t('auth.login') }}</h2>
              <p class="form-subtitle">登录你的账号，继续探索与协作。</p>
            </div>
            <div v-if="inviteLookup" class="invite-banner" role="status">
              <t-icon name="link" class="invite-banner__icon" />
              <div class="invite-banner__text">
                <div class="invite-banner__title">{{ $t('inviteRegister.bannerTitle', { tenant: inviteLookup.tenant_name || '' }) }}</div>
                <div class="invite-banner__hint">{{ $t('inviteRegister.bannerHintLogin') }}</div>
              </div>
            </div>
            <div v-else-if="inviteLookupError" class="invite-banner invite-banner--error" role="alert">{{ inviteLookupError }}</div>
            <div v-else-if="inviteLookupLoading" class="invite-loading" role="status"><t-loading size="small" /><span>正在验证邀请…</span></div>

            <t-form ref="formRef" :data="formData" :rules="formRules" @submit="handleLogin" layout="vertical" label-align="top">
              <t-form-item :label="$t('auth.email')" name="email">
                <t-input v-model="formData.email" :placeholder="$t('auth.emailPlaceholder')" type="text" autocomplete="email" size="large" :disabled="loading" />
              </t-form-item>
              <t-form-item :label="$t('auth.password')" name="password">
                <t-input v-model="formData.password" :placeholder="$t('auth.passwordPlaceholder')" type="password" autocomplete="current-password" size="large" :disabled="loading" @enter="handleLogin" />
              </t-form-item>
              <t-button type="submit" theme="primary" size="large" block :loading="loading" class="submit-button">
                {{ loading ? $t('auth.loggingIn') : $t('auth.login') }}
                <template v-if="!loading" #suffix><t-icon name="arrow-right" size="18px" /></template>
              </t-button>
              <div class="register-cta" v-if="registrationEnabled">
                <span>{{ $t('auth.firstTime') }}</span>
                <button type="button" class="link-button" :disabled="loading" @click="toggleMode">{{ $t('auth.createAccount') }}<t-icon name="arrow-up-right" size="15px" /></button>
              </div>
              <template v-if="oidcEnabled">
                <div class="oidc-divider"><span>{{ $t('auth.orContinueWith') }}</span></div>
                <t-button theme="default" size="large" block :loading="oidcLoading" :disabled="loading" class="oidc-button" @click="handleOIDCLogin">
                  {{ oidcLoading ? $t('auth.redirectingToOIDC') : oidcLoginText }}
                </t-button>
              </template>
            </t-form>
            <div v-if="registrationMode === 'invite_register' && !inviteLookup" class="access-note">
              <t-icon name="mail" size="17px" /><p>首次使用？<br /><span>请向管理员获取邀请链接，创建账号并加入空间。</span></p>
            </div>
            <div v-else-if="registrationMode === 'invite_only'" class="access-note">
              <t-icon name="user" size="17px" /><p>需要访问权限？<br /><span>请联系管理员获取账号或空间邀请。</span></p>
            </div>
          </div>

          <div class="form-card" v-if="isRegisterMode && registrationEnabled">
            <div class="form-heading-mark"><t-icon name="user-add" size="22px" /></div>
            <div class="form-header">
              <p class="form-eyebrow">开始你的 SOLEX 之旅</p>
              <h2 class="form-title">{{ $t('auth.createAccount') }}</h2>
              <p class="form-subtitle">{{ inviteLookup ? '加入团队空间，让知识与经验彼此连接。' : '创建账号，开启你的知识工作空间。' }}</p>
            </div>
            <div v-if="inviteLookup" class="invite-banner" role="status">
              <t-icon name="link" class="invite-banner__icon" />
              <div class="invite-banner__text">
                <div class="invite-banner__title">{{ $t('inviteRegister.bannerTitle', { tenant: inviteLookup.tenant_name || '' }) }}</div>
                <div class="invite-banner__hint">{{ $t('inviteRegister.bannerHint') }}</div>
              </div>
            </div>
            <div v-else-if="inviteLookupError" class="invite-banner invite-banner--error" role="alert">{{ inviteLookupError }}</div>
            <t-form ref="registerFormRef" :data="registerData" :rules="registerRules" @submit="handleRegister" layout="vertical" label-align="top">
              <t-form-item :label="$t('auth.username')" name="username">
                <t-input v-model="registerData.username" :placeholder="$t('auth.usernamePlaceholder')" autocomplete="username" size="large" :disabled="loading" />
              </t-form-item>
              <t-form-item :label="$t('auth.email')" name="email">
                <t-input v-model="registerData.email" :placeholder="$t('auth.emailPlaceholder')" type="text" autocomplete="email" size="large" :disabled="loading" />
              </t-form-item>
              <t-form-item :label="$t('auth.password')" name="password">
                <t-input v-model="registerData.password" :placeholder="$t('auth.passwordPlaceholder')" type="password" autocomplete="new-password" size="large" :disabled="loading" />
              </t-form-item>
              <t-form-item :label="$t('auth.confirmPassword')" name="confirmPassword">
                <t-input v-model="registerData.confirmPassword" :placeholder="$t('auth.confirmPasswordPlaceholder')" type="password" autocomplete="new-password" size="large" :disabled="loading" @enter="handleRegister" />
              </t-form-item>
              <t-button type="submit" theme="primary" size="large" block :loading="loading" class="submit-button">{{ loading ? $t('auth.registering') : $t('auth.register') }}</t-button>
            </t-form>
            <div class="form-footer"><span>{{ $t('auth.haveAccount') }}</span><button type="button" class="link-button" :disabled="loading" @click="toggleMode">{{ $t('auth.backToLogin') }}</button></div>
          </div>
        </div>
        <div class="form-security"><t-icon name="secured" size="15px" /><span>你的企业知识工作空间</span></div>
      </section>
    </main>
    <footer class="login-footer"><span>SOLEX</span><span>知识有序，探索无界。</span></footer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useRoleLabel } from '@/composables/useRoleLabel'
import { notifyLoginSuccess } from '@/utils/loginNotify'
import { canRegister } from './registrationPolicy'
import { newPasswordRules } from '@/utils/passwordPolicy'
import {
  login,
  register,
  getOIDCAuthorizationURL,
  getOIDCConfig,
  autoSetup,
  getAuthConfig,
  userInfoFromApi,
  getInvitationByToken,
  registerByInvite,
  type InviteLookup,
} from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { t, tm, locale } = useI18n()
const { formatRole, roleIcon } = useRoleLabel()

// Form references
const formRef = ref()
const registerFormRef = ref()

// State management
const loading = ref(false)
const oidcLoading = ref(false)
const isRegisterMode = ref(false)
const showLanguageMenu = ref(false)
const oidcEnabled = ref(false)
const oidcProviderName = ref('')
// Wait for configuration before showing a registration entry.
const registrationMode = ref('')
const registrationEnabled = computed(() => canRegister(registrationMode.value, !!inviteLookup.value))
const complexPasswordEnabled = ref(false)

// invite-link state. When the URL carries ?token=xxx we resolve it to
// the originating tenant + role and switch the form into a "register
// via invitation" mode when invitation registration is enabled. Submitting the register
// form with this set hits /auth/register-by-invite (auto-login on
// success) instead of /auth/register.
const inviteToken = ref('')
const inviteLookup = ref<InviteLookup | null>(null)
const inviteLookupError = ref('')
const inviteLookupLoading = ref(false)

// Language options
const languageOptions = [
  { value: 'zh-CN', label: '简体中文', shortLabel: '中文', flag: '🇨🇳' },
  { value: 'zh-TW', label: '繁體中文', shortLabel: '繁中', flag: '繁' },
  { value: 'en-US', label: 'English', shortLabel: 'EN', flag: '🇺🇸' },
  { value: 'ru-RU', label: 'Русский', shortLabel: 'RU', flag: '🇷🇺' },
  { value: 'ko-KR', label: '한국어', shortLabel: '한국어', flag: '🇰🇷' },
  { value: 'ja-JP', label: '日本語', shortLabel: '日本語', flag: '🇯🇵' }
]

const currentLanguage = computed(() => locale.value)
const oidcLoginText = computed(() => {
  if (oidcProviderName.value) {
    return t('auth.oidcLoginWithProvider', { provider: oidcProviderName.value })
  }
  return t('auth.oidcLogin')
})
const currentLangOption = computed(() => languageOptions.find(l => l.value === currentLanguage.value))

// Login form data
const formData = reactive<{ [key: string]: any }>({
  email: '',
  password: '',
})

// Register form data
const registerData = reactive<{ [key: string]: any }>({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

// Login form validation rules
const formRules = computed(() => ({
  email: [
    { required: true, message: t('auth.emailRequired'), type: 'error' },
    { email: true, message: t('auth.emailInvalid'), type: 'error' }
  ],
  password: [
    { required: true, message: t('auth.passwordRequired'), type: 'error' },
    { min: 8, message: t('auth.passwordMinLength'), type: 'error' },
    { max: 32, message: t('auth.passwordMaxLength'), type: 'error' }
  ],
}))

// Register form validation rules
const registerRules = computed(() => ({
  username: [
    { required: true, message: t('auth.usernameRequired'), type: 'error' },
    { min: 2, message: t('auth.usernameMinLength'), type: 'error' },
    { max: 20, message: t('auth.usernameMaxLength'), type: 'error' },
    {
      pattern: /^[a-zA-Z0-9_\u4e00-\u9fa5]+$/,
      message: t('auth.usernameInvalid'),
      type: 'error'
    }
  ],
  email: [
    { required: true, message: t('auth.emailRequired'), type: 'error' },
    { email: true, message: t('auth.emailInvalid'), type: 'error' }
  ],
  password: newPasswordRules(t, complexPasswordEnabled.value),
  confirmPassword: [
    { required: true, message: t('auth.confirmPasswordRequired'), type: 'error' },
    {
      validator: (val: string) => val === registerData.password,
      message: t('auth.passwordMismatch'),
      type: 'error'
    }
  ]
}))

// Toggle login/register mode
const toggleMode = () => {
  isRegisterMode.value = !isRegisterMode.value && registrationEnabled.value

  Object.keys(registerData).forEach(key => {
    (registerData as any)[key] = ''
  })
}

// Toggle language menu
const toggleLanguageMenu = () => {
  showLanguageMenu.value = !showLanguageMenu.value
}

// Select language
const selectLanguage = (lang: string) => {
  locale.value = lang
  localStorage.setItem('locale', lang)
  showLanguageMenu.value = false
  MessagePlugin.success(t('language.languageSaved'))
}

// Close language menu when clicking outside
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.language-switch')) {
    showLanguageMenu.value = false
  }
}

// Add click outside listener
onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})

const persistLoginResponse = async (response: any, skipRedirect = false) => {
  // Backend renamed `tenant` to `active_tenant` and added `memberships`
  // when tenant-level RBAC landed (issue #1303). The two are otherwise
  // identical — `active_tenant` is the tenant whose ID is encoded in the
  // JWT, defaulting to the user's home tenant on a fresh login.
  const activeTenant = response.active_tenant || response.tenant
  if (response.user && response.token) {
    // user.tenant_id must be the user's HOME tenant (the immutable row
    // on the users table); useHomeTenant() and the home-badge logic both
    // assume so. The ACTIVE tenant (which can differ from home when the
    // server honoured a remembered last-active-tenant preference) is
    // expressed separately via setSelectedTenant below.
    const homeTenantIdRaw = response.user.tenant_id ?? activeTenant?.id ?? ''
    authStore.setUser(userInfoFromApi(response.user, homeTenantIdRaw))
    authStore.setToken(response.token)
    if (response.refresh_token) {
      authStore.setRefreshToken(response.refresh_token)
    }
    if (activeTenant) {
      authStore.setTenant({
        id: String(activeTenant.id) || '',
        name: activeTenant.name || '',
        owner_id: response.user.id || '',
        created_at: activeTenant.created_at || new Date().toISOString(),
        updated_at: activeTenant.updated_at || new Date().toISOString()
      })
    } else {
      authStore.setTenant(null)
    }
    if (Array.isArray(response.memberships)) {
      authStore.setMemberships(response.memberships)
    }
    // If the backend dropped us into a non-home tenant (honoured a
    // remembered "last active tenant" preference), set the override so
    // subsequent requests carry X-Tenant-ID and the UI stays consistent.
    // Otherwise clear any stale override left in localStorage by a
    // previous session for a different account.
    const activeIdNum = Number(activeTenant?.id)
    const homeIdNum = Number(homeTenantIdRaw)
    if (Number.isFinite(activeIdNum) && Number.isFinite(homeIdNum) && activeIdNum !== homeIdNum) {
      authStore.setSelectedTenant(activeIdNum, activeTenant?.name || null)
    } else {
      authStore.setSelectedTenant(null, null)
    }
  }

  // Pull runtime capabilities (including whether ordinary users may create
  // workspaces) before entering the main UI so create actions never flash
  // briefly when the deployment is invitation-only.
  await authStore.refreshFromAuthMe()
  await nextTick()
  if (skipRedirect) return
  router.replace(authStore.hasValidTenant ? '/platform/knowledge-bases' : '/onboarding/workspace')
}

const getBackendOIDCRedirectURI = () => `${window.location.origin}/api/v1/auth/oidc/callback`

const loadOIDCConfig = async () => {
  try {
    const response = await getOIDCConfig()
    oidcEnabled.value = !!response.success && !!response.enabled
    oidcProviderName.value = response.provider_display_name || ''
  } catch {
    oidcEnabled.value = false
    oidcProviderName.value = ''
  }
}

// Registration stays hidden if configuration cannot be loaded.
const loadAuthConfig = async () => {
  try {
    const response = await getAuthConfig()
    registrationMode.value = response.success ? response.registration_mode : ''
    complexPasswordEnabled.value = response.complex_password_enabled
  } catch {
    registrationMode.value = ''
    complexPasswordEnabled.value = false
  }
}

const handleOIDCLogin = async () => {
  try {
    oidcLoading.value = true
    const response = await getOIDCAuthorizationURL(getBackendOIDCRedirectURI())
    const authorizationURL = response.authorization_url

    if (!response.success || !authorizationURL) {
      MessagePlugin.error(response.message || t('auth.oidcLoginFailed'))
      return
    }

    // 跳转 IdP 会丢失 URL 中的 token，暂存到 sessionStorage，回调后由 App.vue 兑换。
    if (inviteToken.value) {
      sessionStorage.setItem('weknora_pending_invite_token', inviteToken.value)
    }
    window.location.href = authorizationURL
  } catch (error: any) {
    console.error('OIDC 登录跳转失败:', error)
    MessagePlugin.error(error.message || t('auth.oidcLoginFailed'))
  } finally {
    oidcLoading.value = false
  }
}

// 用 token 加入空间并进入应用。会话此时已有效，故即便 token 失效也照常进入（避免困在登录页）。
const acceptAndEnter = async (token: string) => {
  loading.value = true
  try {
    const result = await authStore.acceptInvitationByTokenAndRefresh(token)
    if (result.ok) {
      MessagePlugin.success(t('inviteRegister.joined'))
    } else {
      MessagePlugin.warning(t('inviteRegister.invalidBody'))
    }
  } catch {
    MessagePlugin.warning(t('inviteRegister.invalidBody'))
  } finally {
    loading.value = false
    await nextTick()
    router.replace('/platform/knowledge-bases')
  }
}

// Handle login
const handleLogin = async () => {
  try {
    const valid = await formRef.value?.validate()
    if (valid !== true) return

    loading.value = true

    const response = await login({
      email: formData.email,
      password: formData.password,
    })

    if (response.success) {
      if (inviteToken.value) {
        // 从邀请链接登录：持久化会话后兑换 token 并进入对应空间。
        await persistLoginResponse(response, true)
        await acceptAndEnter(inviteToken.value)
        return
      }
      await persistLoginResponse(response)
      notifyLoginSuccess(response, t, tm, formatRole, roleIcon)
    } else {
      MessagePlugin.error(response.message || t('auth.loginError'))
    }
  } catch (error: any) {
    console.error('登录错误:', error)
    MessagePlugin.error(error.message || t('auth.loginErrorRetry'))
  } finally {
    loading.value = false
  }
}

// Handle registration. Dispatches based on whether the user arrived
// with a share-link token: with token -> register-by-invite (auto-
// login on success); without -> the normal self-service register
// (drops back to the login form for the user to sign in).
const handleRegister = async () => {
  if (!registrationEnabled.value) return
  try {
    const valid = await registerFormRef.value?.validate()
    if (valid !== true) return

    loading.value = true

    if (inviteToken.value) {
      const response = await registerByInvite({
        token: inviteToken.value,
        username: registerData.username,
        email: registerData.email,
        password: registerData.password,
      })
      if (!response.success) {
        MessagePlugin.error(response.message || t('auth.registerFailed'))
        return
      }
      MessagePlugin.success(t('auth.registerSuccess'))
      // register-by-invite returns the same shape as login (token +
      // active_tenant + memberships), so reuse the login persistence
      // path — same store writes, same redirect target.
      await persistLoginResponse(response)
      return
    }

    const response = await register({
      username: registerData.username,
      email: registerData.email,
      password: registerData.password
    })

    if (response.success) {
      MessagePlugin.success(t('auth.registerSuccess'))

      // Switch to login mode and fill in email
      isRegisterMode.value = false
      formData.email = registerData.email

      // Clear register form
      Object.keys(registerData).forEach(key => {
        (registerData as any)[key] = ''
      })
    } else {
      MessagePlugin.error(response.message || t('auth.registerFailed'))
    }
  } catch (error: any) {
    console.error('注册错误:', error)
    MessagePlugin.error(error.message || t('auth.registerError'))
  } finally {
    loading.value = false
  }
}

// Check if already logged in; for lite edition, attempt transparent auto-setup
onMounted(async () => {
  // Share-link landing: ?token=xxx switches the form into invite-
  // register mode before any other auto-flow (logged-in redirect /
  // auto-setup / OIDC) gets a chance to redirect. Resolution failure
  // surfaces inline; the user can still log in normally if they
  // already have an account. We check this BEFORE the isLoggedIn
  // redirect so an existing session doesn't bounce the user to
  // /platform (and possibly back to /login if the session is stale),
  // dropping the invite token along the way.
  const tokenFromQuery = String(route.query.token || '').trim()
  if (tokenFromQuery) {
    inviteToken.value = tokenFromQuery
    inviteLookupLoading.value = true
    // 1. 先校验 token：无效/过期则停在登录页报错，不进注册模式。
    try {
      const resp = await getInvitationByToken(tokenFromQuery)
      if (resp.success && resp.data) {
        inviteLookup.value = resp.data
      } else {
        inviteLookupError.value = resp.message || t('inviteRegister.invalidBody')
        loadOIDCConfig()
        loadAuthConfig()
        return
      }
    } catch {
      inviteLookupError.value = t('inviteRegister.invalidBody')
      loadOIDCConfig()
      loadAuthConfig()
      return
    } finally {
      inviteLookupLoading.value = false
    }

    // 2. 已登录则直接兑换 token 进入空间（三种模式通用）。
    if (authStore.isLoggedIn && (await authStore.refreshFromAuthMe())) {
      await acceptAndEnter(tokenFromQuery)
      return
    }

    // 3. Only enabled registration modes may create an invited account.
    await loadAuthConfig()
    isRegisterMode.value = registrationEnabled.value
    loadOIDCConfig()
    return
  }

  if (authStore.isLoggedIn) {
    router.replace('/platform/knowledge-bases')
    return
  }

  localStorage.removeItem('weknora_auto_setup_failed')
  try {
    const response = await autoSetup()
    if (response.success) {
      authStore.setLiteMode(true)
      await persistLoginResponse(response)
      return
    }
  } catch {
    // Auto-setup may be unavailable outside the native Lite shell.
  }

  loadOIDCConfig()
  loadAuthConfig()
})
</script>

<style lang="less" scoped>
.login-layout {
  --login-ink: #172d35;
  --login-muted: #6d8086;
  --login-accent: #087f8c;
  --login-line: #dce7e7;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  color: var(--login-ink);
  background: #f5f8f8;
}

.login-header {
  width: min(1320px, 100%);
  margin: 0 auto;
  padding: 30px 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  box-sizing: border-box;
}

.header-logo { display: flex; align-items: center; gap: 20px; }
.logo-image { display: block; width: 128px; height: 32px; object-fit: contain; }
.brand-divider { width: 1px; height: 19px; background: #cddbdc; }
.brand-caption { color: #647c82; font-size: var(--app-text-md); letter-spacing: .06em; }
.language-switch { position: relative; z-index: 10; }
.language-trigger { display: flex; align-items: center; gap: 8px; border: 1px solid var(--login-line); border-radius: var(--app-radius-md); padding: 9px 12px; color: #526a72; background: rgba(255,255,255,.75); cursor: pointer; font: inherit; font-size: var(--app-text-md); }
.language-trigger:hover { background: #fff; border-color: #9bbfc1; }
.language-trigger:focus-visible, .language-option:focus-visible, .link-button:focus-visible { outline: 2px solid var(--login-accent); outline-offset: 3px; }
.language-dropdown { position: absolute; top: calc(100% + 8px); right: 0; min-width: 150px; padding: 6px; border: 1px solid var(--login-line); border-radius: var(--app-radius-lg); background: #fff; box-shadow: 0 12px 32px #172d3510; }
.language-option { display: flex; justify-content: space-between; align-items: center; gap: 16px; width: 100%; padding: 10px; border: 0; border-radius: var(--app-radius-xs); color: #526a72; background: transparent; text-align: left; cursor: pointer; font-size: var(--app-text-md); }
.language-option:hover, .language-option.active { color: var(--login-accent); background: #edf7f7; }

.login-main { flex: 1; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(360px, .85fr); align-items: center; gap: clamp(52px, 7vw, 112px); width: min(1160px, calc(100% - 96px)); margin: 0 auto; padding: 35px 0 45px; }
.showcase-section { min-width: 0; }
.showcase-eyebrow { display: flex; align-items: center; gap: 9px; color: var(--login-accent); font-size: var(--app-text-sm); font-weight: 600; letter-spacing: .12em; }
.showcase-eyebrow > span { width: 6px; height: 6px; border-radius: var(--solex-radius-micro); background: var(--login-accent); }
h1 { margin: 24px 0 22px; font-size: clamp(36px, 3.7vw, 54px); font-weight: 600; line-height: 1.3; letter-spacing: -.045em; }
.headline-accent { color: var(--login-accent); }
.showcase-description { color: #6b7f85; font-size: var(--app-text-lg); line-height: 1.9; margin: 0 0 33px; }
.knowledge-map { max-width: 520px; overflow: hidden; border: 1px solid var(--login-line); border-radius: var(--solex-radius-panel); background: rgba(255,255,255,.65); }
.map-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 17px 20px 0; color: #667d83; font-size: var(--app-text-xs); }
.map-caption { font-size: var(--solex-text-micro); color: #91a4aa; letter-spacing: .08em; }
.map-canvas { height: 218px; position: relative; margin: 0 15px; }
.map-connections { position: absolute; width: 100%; height: 100%; inset: 0; overflow: visible; }
.map-connections path { fill: none; stroke: #ccdfe0; stroke-width: 1.4px; vector-effect: non-scaling-stroke; }
.map-connections path.map-connection-active { stroke: #85b7ba; }
.map-connections circle { fill: #97bfc2; }
.source-nodes { position: absolute; top: 28px; width: 100%; display: grid; grid-template-columns: repeat(3, 1fr); gap: 13px; }
.source-node { height: 43px; display: flex; align-items: center; justify-content: center; gap: 9px; border: 1px solid #e0e9e9; border-radius: var(--app-radius-lg); background: #fff; color: #536e76; font-size: var(--app-text-sm); box-shadow: 0 3px 8px #203a4203; }
.source-node :deep(.t-icon) { color: #7f9fa5; }
.knowledge-hub { position: absolute; left: 50%; top: 91px; transform: translateX(-50%); display: flex; align-items: center; gap: 9px; padding: 10px 15px; border: 1px solid #c9e2e3; border-radius: var(--app-radius-lg); color: #1d606b; background: #edf7f7; box-shadow: 0 0 0 7px #f7fafa; font-size: var(--app-text-sm); font-weight: 600; white-space: nowrap; }
.knowledge-hub img { width: 22px; height: 22px; }
.hub-dot { width: 5px; height: 5px; border-radius: 50%; background: #087f8c; margin-left: 7px; }
.knowledge-outcome { position: absolute; top: 174px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; justify-content: center; gap: 11px; width: 290px; max-width: 95%; padding: 12px 10px; box-sizing: border-box; background: #fff; border: 1px solid #e0e9e9; border-radius: var(--app-radius-md); color: #526d74; font-size: var(--app-text-sm); }
.knowledge-outcome :deep(.t-icon:first-child) { color: var(--login-accent); }
.knowledge-outcome :deep(.t-icon:last-child) { margin-left: auto; color: #8ca7ab; }
.map-footer { display: flex; justify-content: space-between; padding: 16px 20px; margin-top: 12px; border-top: 1px solid #e6eded; color: #82969c; font-size: var(--app-text-xs); }
.map-footer > span { display: flex; align-items: center; gap: 5px; }
.map-footer :deep(.t-icon) { color: #5b9a9e; }
.showcase-note { margin: 17px 0 0; color: #8a9da2; font-size: var(--app-text-xs); }

.form-section { min-width: 0; width: 100%; max-width: 440px; justify-self: end; }
.form-panel { border: 1px solid var(--login-line); border-radius: var(--solex-radius-card); background: #fff; box-shadow: 0 22px 60px -24px #234b5620, 0 2px 8px #234b5603; }
.form-card { padding: 36px 36px 30px; }
.form-heading-mark { width: 42px; height: 42px; border-radius: var(--app-radius-xl); display: grid; place-items: center; color: var(--login-accent); background: #edf7f7; border: 1px solid #deeeee; margin-bottom: 23px; }
.form-header { margin-bottom: 26px; }
.form-eyebrow { margin: 0 0 9px; color: #879a9f; font-size: var(--app-text-xs); letter-spacing: .06em; }
.form-title { margin: 0; font-size: var(--solex-text-heading-lg); font-weight: 600; line-height: 1.3; letter-spacing: -.025em; }
.form-subtitle { margin: 10px 0 0; font-size: var(--app-text-sm); color: #7a8d93; line-height: 1.8; }
.form-card :deep(.t-form__item) { margin-bottom: 20px; }
.form-card :deep(.t-form__label) { color: #435d65; font-size: var(--app-text-sm); font-weight: 500; padding-bottom: 8px; line-height: 1.5; }
.form-card :deep(.t-form__label--required label::before) { display: none; }
.form-card :deep(.t-input) { min-height: 46px; background: #fbfdfd; border: 1px solid #dbe6e7; border-radius: var(--app-radius-md); font-size: var(--app-text-md); padding: 0 13px; }
.form-card :deep(.t-input:hover) { border-color: #9dbfc3; }
.form-card :deep(.t-input--focused) { border-color: var(--login-accent); box-shadow: 0 0 0 3px #087f8c0d; background: #fff; }
.form-card :deep(.t-input__inner) { color: var(--login-ink); }
.form-card :deep(.t-input__inner::placeholder) { color: #a3b1b5; }
.form-card :deep(.t-input--error) { border-color: var(--td-error-color); }
.submit-button { min-height: 46px; margin-top: 7px; border-radius: var(--app-radius-md); border-color: var(--login-accent); background: var(--login-accent); font-size: var(--app-text-base); letter-spacing: .03em; box-shadow: 0 5px 12px #087f8c12; }
.submit-button:hover { background: #076c78; border-color: #076c78; }
.register-cta, .form-footer { display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 23px; font-size: var(--app-text-sm); color: #81959b; }
.link-button { display: inline-flex; align-items: center; gap: 4px; border: 0; border-radius: var(--solex-radius-micro); padding: 2px; color: var(--login-accent); background: transparent; font-size: var(--app-text-sm); font-weight: 500; cursor: pointer; }
.link-button:hover { color: #065f6a; }
.link-button:disabled { opacity: .5; cursor: not-allowed; }
.access-note { display: flex; gap: 10px; align-items: flex-start; margin-top: 25px; padding: 17px 0 0; border-top: 1px solid #edf1f2; color: #9aadb2; }
.access-note > :deep(.t-icon) { flex-shrink: 0; margin-top: 2px; }
.access-note p { margin: 0; font-size: var(--app-text-xs); color: #697f86; line-height: 1.8; }
.access-note p span { color: #91a2a8; }
.form-security { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 20px; color: #91a4a9; font-size: var(--app-text-xs); }
.oidc-divider { display: flex; align-items: center; gap: 12px; margin: 22px 0; color: #91a2a8; font-size: var(--app-text-xs); }
.oidc-divider::before, .oidc-divider::after { content: ''; height: 1px; flex: 1; background: #e8eeef; }
.oidc-button { min-height: 44px; border-radius: var(--app-radius-md); font-size: var(--app-text-md); background: #fff; border-color: var(--login-line); color: #435d65; }
.invite-banner { display: flex; gap: 10px; padding: 13px; margin-bottom: 22px; border: 1px solid #dceced; border-radius: var(--app-radius-lg); color: #326f76; background: #f2f9f9; line-height: 1.7; font-size: var(--app-text-sm); }
.invite-banner__icon { flex-shrink: 0; margin-top: 2px; }
.invite-banner__title { font-weight: 500; overflow-wrap: anywhere; }
.invite-banner__hint { margin-top: 4px; color: #7a9297; font-size: var(--app-text-xs); }
.invite-banner--error { color: #b04444; border-color: #f1d9d9; background: #fff7f7; }
.invite-loading { display: flex; align-items: center; gap: 9px; margin-bottom: 20px; font-size: var(--app-text-sm); color: #6d8086; }
.login-footer { display: flex; justify-content: space-between; gap: 16px; padding: 23px 48px; border-top: 1px solid #e5eded; color: #94a6ab; font-size: var(--app-text-2xs); letter-spacing: .04em; }
.login-footer > span:first-child { font-weight: 600; letter-spacing: .13em; }

@media (max-width: 1024px) {
  .login-header { padding: 26px 32px; }
  .login-main { width: calc(100% - 64px); grid-template-columns: minmax(0, 1fr) minmax(330px, .9fr); gap: 40px; }
  .form-card { padding: 30px 26px; }
  .map-caption { display: none; }
  .source-nodes { gap: 7px; }
  .source-node { gap: 6px; font-size: var(--app-text-xs); }
  .map-heading, .map-footer { padding-left: 15px; padding-right: 15px; }
}

@media (max-width: 768px) {
  .login-header { padding: 23px 24px; }
  .brand-divider, .brand-caption { display: none; }
  .login-main { display: flex; flex-direction: column; gap: 36px; width: min(440px, calc(100% - 40px)); padding: 24px 0 36px; }
  .form-section { order: -1; width: 100%; }
  .form-card { padding: 30px; }
  .showcase-section { width: 100%; }
  .showcase-eyebrow { font-size: var(--app-text-2xs); }
  h1 { margin: 14px 0 12px; font-size: var(--solex-text-display); }
  .showcase-description { font-size: var(--app-text-md); margin-bottom: 22px; }
  .knowledge-map, .showcase-note { display: none; }
  .login-footer { padding: 18px 24px; }
}

@media (max-width: 480px) {
  .login-header { padding: 21px 20px; }
  .logo-image { width: 108px; height: 28px; }
  .language-trigger { padding: 8px 10px; gap: 6px; }
  .form-card { padding: 27px 24px; }
  .form-panel { border-radius: var(--solex-radius-panel); }
  .form-heading-mark { margin-bottom: 20px; }
  .form-title { font-size: var(--solex-text-heading); }
  .form-security { margin-top: 17px; }
  .login-main { padding-top: 15px; }
  .login-footer { padding: 16px 20px; }
}
</style>
