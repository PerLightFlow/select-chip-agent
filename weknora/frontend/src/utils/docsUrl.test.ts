import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { DOC_PAGES, docsUrl, resolveDocumentationUrl } from './docsUrl'

test('every help topic stays inside the authenticated settings route', () => {
  for (const page of Object.keys(DOC_PAGES) as Array<keyof typeof DOC_PAGES>) {
    const url = new URL(docsUrl(page), 'https://company.example')
    assert.equal(url.origin, 'https://company.example')
    assert.equal(url.pathname, '/platform/settings')
    assert.equal(url.searchParams.get('section'), 'help')
    assert.equal(url.searchParams.get('topic'), page)
  }
})

test('product documentation links use local help, including compatibility anchors', () => {
  assert.equal(resolveDocumentationUrl('https://weknora.weixin.qq.com/docs/03-features/06-models'), docsUrl('models'))
  assert.equal(resolveDocumentationUrl('https://weknora.weixin.qq.com/docs/03-features/06-models#协议兼容覆盖-compat-json'), docsUrl('modelsCompat'))
  assert.equal(resolveDocumentationUrl('https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md'), docsUrl('apiOverview'))
  assert.equal(resolveDocumentationUrl('https://github.com/Tencent/WeKnora/issues/new'), docsUrl('home'))
})

test('research sources and unrelated repositories are preserved', () => {
  for (const url of ['https://www.espressif.com/en/products/socs', 'https://github.com/Tencent/WeKnora-example', 'https://weknora.weixin.qq.com.example.org/docs/']) {
    assert.equal(resolveDocumentationUrl(url), url)
  }
})

test('unsupported schemes and malformed input are inert', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,test', '/relative', '', null, {}]) {
    assert.equal(resolveDocumentationUrl(value), '')
  }
  assert.equal(resolveDocumentationUrl('https://weknora.weixin.qq.com/docs/%ZZ'), docsUrl('home'))
})
