import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./Login.vue', import.meta.url), 'utf8')
const tabletStyles = source.slice(
  source.indexOf('@media (max-width: 768px)'),
  source.indexOf('@media (max-width: 480px)'),
)
const phoneStyles = source.slice(source.indexOf('@media (max-width: 480px)'))

test('phone login keeps the form ahead of the showcase with a header in document flow', () => {
  assert.match(tabletStyles, /\.login-main\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/)
  assert.match(tabletStyles, /\.form-section\s*\{[^}]*order:\s*-1;/)
  const headerStyles = source.match(/\.login-header\s*\{([^}]+)\}/)?.[1] || ''
  assert.doesNotMatch(headerStyles, /position:\s*(?:absolute|fixed)/)
})

test('narrow login headers hide the brand caption and keep the language control visible', () => {
  assert.match(tabletStyles, /\.brand-divider,\s*\.brand-caption\s*\{\s*display:\s*none;/)
  assert.match(phoneStyles, /\.logo-image\s*\{[^}]*width:\s*108px;/)
  assert.match(source, /class="language-trigger"[\s\S]*?:aria-expanded="showLanguageMenu"/)
})
