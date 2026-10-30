import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import test from 'node:test'
import * as vue from 'vue'
import * as pinia from 'pinia'
import ts from 'typescript'

const source = readFileSync(new URL('./assistant.ts', import.meta.url), 'utf8')

function fixture(displayName: string) {
  const config = { display_name: displayName, max_access_level: 'confirm' }
  const auth = vue.reactive({ user: { id: 'test-user' }, effectiveTenantId: 1 })
  const storage = { getItem: () => null, setItem() {}, removeItem() {} }
  const dependencies: Record<string, unknown> = {
    vue, pinia,
    './auth': { useAuthStore: () => auth },
    '@/api/assistant': {
      DEFAULT_ASSISTANT_ACCESS_LEVEL: 'confirm',
      capAssistantAccessLevel: (level: string) => level,
      isAssistantAccessLevel: (level: string) => ['read_only', 'confirm', 'auto_write'].includes(level),
      getTenantAssistantConfig: async () => ({ data: config }),
    },
  }
  const exports: any = {}
  runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, {
    exports, console, localStorage: storage, sessionStorage: storage,
    require(name: string) {
      assert.ok(name in dependencies, `Unexpected dependency: ${name}`)
      return dependencies[name]
    },
  })
  const root = pinia.createPinia()
  pinia.setActivePinia(root)
  const assistant = exports.useAssistantStore()
  return { assistant, config, close: () => pinia.disposePinia(root) }
}

test('the old workspace assistant default displays as SOLEX without changing the response', async () => {
  const f = fixture(' WeKnora ')
  try {
    await f.assistant.loadWorkspaceConfig()
    assert.equal(f.assistant.displayName, 'SOLEX')
    assert.equal(f.assistant.workspaceConfig.display_name, 'SOLEX')
    assert.equal(f.config.display_name, ' WeKnora ')
    assert.equal(f.assistant.accessCeiling, 'confirm')
    f.assistant.setWorkspaceConfig({ display_name: 'weknora', max_access_level: 'read_only' })
    assert.equal(f.assistant.displayName, 'SOLEX')
    assert.equal(f.assistant.accessCeiling, 'read_only')
  } finally { f.close() }
})

test('custom workspace names and empty defaults preserve their meaning', async () => {
  const f = fixture('WeKnora 迁移助手')
  try {
    await f.assistant.loadWorkspaceConfig()
    assert.equal(f.assistant.displayName, 'WeKnora 迁移助手')
    f.assistant.setWorkspaceConfig({ display_name: '', max_access_level: 'confirm' })
    assert.equal(f.assistant.displayName, '')
    f.assistant.setWorkspaceConfig({ display_name: '团队助手', max_access_level: 'confirm' })
    assert.equal(f.assistant.displayName, '团队助手')
  } finally { f.close() }
})
