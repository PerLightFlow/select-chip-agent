/** Product help lives in the current authenticated workspace. */
export const DOCS_BASE_URL = '/platform/settings?section=help'

/**
 * Doc pages linked from the UI, as website-docs paths without the `.md`
 * suffix. docsUrl.test.ts checks each one (and its anchor) still exists.
 */
export const DOC_PAGES = {
  home: '',
  tenantAuth: '03-features/01-tenant-auth',
  models: '03-features/06-models',
  modelsCompat: '03-features/06-models#协议兼容覆盖-compat-json',
  knowledgeGraph: '03-features/09-knowledge-graph',
  imIntegration: '03-features/12-im-integration',
  apiOverview: '04-api/01-api-overview',
  troubleshootingMigrations: '01-getting-started/05-troubleshooting#database-migrations',
  sandboxDeployment: '06-development/04-sandbox-deployment',
} as const

export type DocPage = keyof typeof DOC_PAGES

export function docsUrl(page: DocPage): string {
  return `${DOCS_BASE_URL}&topic=${page}`
}

/** Redirect only product documentation; research and provider sources stay intact. */
export function resolveDocumentationUrl(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return ''
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return ''
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return ''
  const repositoryPath = url.pathname.toLowerCase()
  const isProductSite = url.hostname === 'weknora.weixin.qq.com'
  const isProductRepository = url.hostname === 'github.com'
    && /^\/tencent\/weknora(?:\/|$)/.test(repositoryPath)
  if (!isProductSite && !isProductRepository) return url.href
  let locator = url.pathname + url.hash
  try { locator = decodeURIComponent(locator) } catch { /* Keep malformed URL text inert. */ }
  for (const [page, target] of Object.entries(DOC_PAGES).reverse()) {
    if (target && locator.includes(target)) return docsUrl(page as DocPage)
  }
  return docsUrl('home')
}
