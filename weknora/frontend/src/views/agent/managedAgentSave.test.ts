import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import { managedAgentConfig } from '../../config/managedRuntime'

const source = readFileSync(new URL('./AgentEditorModal.vue', import.meta.url), 'utf8')
const save = source.match(/const handleSave = async \(\) => \{[\s\S]*?\n\};\n<\/script>/)?.[0].replace('\n</script>', '')
assert.ok(save)

function harness(managed: boolean) {
  const errors: string[] = []
  const saved: any[] = []
  const context: any = {
    managedRuntime: { value: managed }, isBuiltinAgent: { value: false }, isAgentMode: { value: true },
    formData: { value: { name: 'Personal hardware agent', config: {
      system_prompt: 'Answer hardware questions', model_id: '',
      question_suggestions: { starters: { items: ['Which chip?'] } },
      allowed_tools: ['web_search'], web_search_enabled: true,
    } } },
    currentSection: { value: 'basic' }, editorMode: { value: 'create' }, hostOnly: { value: false },
    saving: { value: false }, savedAgent: { value: null }, storedToolNames: { value: [] }, keepAllowedToolsUnset: { value: false },
    promptTemplates: { value: null }, MessagePlugin: { error: (x: string) => errors.push(x), success() {} },
    t: (key: string) => key, hasPlaceholder: () => true, pruneSelectedSkills() {},
    allowedToolsToSave: () => ['web_search'], serializeAgentPrompts: (c: any) => c, managedAgentConfig,
    createAgent: async (payload: any) => { saved.push(payload); return { data: { id: 'agent-1', config: payload.config } } },
    normalizeLegacyToolNames: (x: unknown) => x, modalShell: { markClean() {} },
    markContextualGuideDone() {}, loadAgentIntegrationCounts() {}, notifyAllowedToolsWarnings() {}, emit() {},
  }
  const code = ts.transpileModule(save + '\nglobalThis.save = handleSave', { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  runInNewContext(code, context)
  return { context, errors, saved }
}

test('ordinary managed user can save a personal agent without choosing a model', async () => {
  const h = harness(true)
  await h.context.save()
  assert.deepEqual(h.errors, [])
  assert.equal(h.saved.length, 1)
  assert.equal(h.saved[0].config.model_id, undefined)
  assert.equal(h.saved[0].config.system_prompt, 'Answer hardware questions')
  assert.equal(h.context.saving.value, false)
})

test('unmanaged editor still requires a model and does not submit an incomplete agent', async () => {
  const h = harness(false)
  await h.context.save()
  assert.deepEqual(h.errors, ['agent.editor.modelRequired'])
  assert.equal(h.saved.length, 0)
})
