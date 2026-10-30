import assert from 'node:assert/strict'
import test from 'node:test'
import { brandBuiltinAgent, builtinAgentDisplayText } from './branding.ts'

test('built-in display fields use SOLEX while protocol and prompt content remain unchanged', () => {
  const original = {
    id: 'builtin-weknora-assistant',
    name: 'WeKnora 助手',
    description: '解答 WeKnora 用法',
    is_builtin: true,
    config: { system_prompt: 'WeKnora protocol prompt', allowed_tools: ['search_weknora_docs'] },
  }
  const branded = brandBuiltinAgent(original)
  assert.equal(branded.name, 'SOLEX 助手')
  assert.equal(branded.description, '解答 SOLEX 用法')
  assert.equal(branded.id, original.id)
  assert.strictEqual(branded.config, original.config)
  assert.equal(original.name, 'WeKnora 助手', 'source records are not mutated')
})

test('user-created agents and unknown built-in IDs are never rewritten', () => {
  for (const id of ['agent-123', 'builtin-customer-created', 'builtin-weknora-assistant-copy']) {
    const agent = { id, name: 'WeKnora 迁移项目', description: 'WeKnora 原始资料', is_builtin: false }
    assert.strictEqual(brandBuiltinAgent(agent), agent)
    assert.equal(builtinAgentDisplayText(id, agent.name), agent.name)
  }
})

test('server-localized built-in labels keep their language and missing descriptions', () => {
  for (const name of ['WeKnora Assistant', 'WeKnora アシスタント', 'WeKnora 어시스턴트']) {
    assert.equal(builtinAgentDisplayText('builtin-weknora-assistant', name), name.replace('WeKnora', 'SOLEX'))
  }
  const agent = { id: 'builtin-quick-answer', name: '快速问答' }
  assert.strictEqual(brandBuiltinAgent(agent), agent)
  const withoutDescription: { id: string; name: string; description?: string } = { id: 'builtin-weknora-assistant', name: 'WeKnora' }
  assert.equal(brandBuiltinAgent(withoutDescription).description, undefined)
})
