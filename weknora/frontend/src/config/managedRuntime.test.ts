import assert from 'node:assert/strict'
import test from 'node:test'
import { reactive } from 'vue'
import { managedAgentConfig, managedKnowledgePayload, managedSettingsSectionAllowed, usesManagedRuntime } from './managedRuntime'

test('central management constrains ordinary workspace Owners, not system administrators', () => {
  const employeeOwner = usesManagedRuntime(true, false)
  for (const section of ['models', 'defaults', 'mcp', 'skills', 'sandbox', 'parser', 'storage', 'websearch', 'ollama', 'envvars']) {
    assert.equal(managedSettingsSectionAllowed(section, employeeOwner), false, section)
    assert.equal(managedSettingsSectionAllowed(section, usesManagedRuntime(true, true)), true, section)
    assert.equal(managedSettingsSectionAllowed(section, usesManagedRuntime(false, false)), true, section)
  }
  for (const section of ['general', 'tenant', 'members', 'browserconnection', 'mymemory', 'assistant', 'userprofile']) {
    assert.equal(managedSettingsSectionAllowed(section, employeeOwner), true, section)
  }
})

test('saving an old reactive agent discards hidden overrides and preserves business choices without mutating the draft', () => {
  const draft = reactive({ model_id: 'old-model', temperature: 0.6, sandbox_config_id: 'old-sandbox',
    web_search_provider_id: 'private-search', system_prompt: 'Help with hardware',
    knowledge_bases: ['enterprise-kb'], allowed_tools: ['web_search'], web_search_enabled: true,
    question_suggestions: { follow_ups: { model_id: 'old-followup', enabled: true } },
  })
  const config = managedAgentConfig(draft, true)
  assert.equal(config.model_id, undefined)
  assert.equal(config.temperature, undefined)
  assert.equal(config.sandbox_config_id, undefined)
  assert.equal(config.web_search_provider_id, undefined)
  assert.equal(config.question_suggestions.follow_ups.model_id, undefined)
  assert.equal(config.question_suggestions.follow_ups.enabled, true)
  assert.deepEqual(config.knowledge_bases, ['enterprise-kb'])
  assert.deepEqual(config.allowed_tools, ['web_search'])
  assert.equal(config.web_search_enabled, true)
  assert.equal(draft.model_id, 'old-model')
  assert.equal(managedAgentConfig(draft, false), draft)
})

test('new KBs omit model and storage bindings while retaining Wiki authoring choices', () => {
  const payload = { name: 'Project A', summary_model_id: 'cached-chat', embedding_model_id: 'cached-embed',
    storage_config: { provider: 'local' }, chunking_config: { chunk_size: 512 },
    wiki_config: { synthesis_model_id: 'cached-wiki', content_instructions: 'Track chip revisions' },
  }
  const result = managedKnowledgePayload(payload, true)
  assert.equal(result.summary_model_id, undefined)
  assert.equal(result.embedding_model_id, undefined)
  assert.equal(result.storage_config, undefined)
  assert.equal(result.chunking_config, undefined)
  assert.equal(result.wiki_config.synthesis_model_id, undefined)
  assert.equal(result.wiki_config.content_instructions, 'Track chip revisions')
  assert.equal(managedKnowledgePayload(payload, false), payload)
})

test('unknown or failed capabilities hide technical setup without removing business modules', () => {
  const restricted = usesManagedRuntime(false, false, false)
  assert.equal(managedSettingsSectionAllowed('models', restricted), false)
  assert.equal(managedSettingsSectionAllowed('tenant', restricted), true)
  assert.equal(managedSettingsSectionAllowed('mymemory', restricted), true)
  assert.equal(usesManagedRuntime(false, true, false), false)
  assert.equal(usesManagedRuntime(false, false, true), false)
})
