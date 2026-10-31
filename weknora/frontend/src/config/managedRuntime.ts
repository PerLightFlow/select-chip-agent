/** Presentation and request shaping for deployments with centrally managed models/tools.
 * Server authorization remains authoritative, including for workspace Owners.
 */
export function usesManagedRuntime(enabled: boolean, isSystemAdmin: boolean, capabilityKnown = true): boolean {
  return (enabled || !capabilityKnown) && !isSystemAdmin
}

const INFRASTRUCTURE_SECTIONS = new Set([
  'models', 'ollama', 'weknoracloud', 'defaults', 'websearch', 'chathistory',
  'vectorstore', 'parser', 'storage', 'sandbox', 'skills', 'mcp', 'memory', 'envvars',
])
export function managedSettingsSectionAllowed(section: string, managed: boolean): boolean {
  return !managed || !INFRASTRUCTURE_SECTIONS.has(section)
}

const AGENT_RUNTIME_FIELDS = [
  'model_id', 'rerank_model_id', 'query_understand_model_id', 'vlm_model_id', 'asr_model_id',
  'temperature', 'max_completion_tokens', 'thinking', 'reasoning_effort', 'max_iterations',
  'llm_call_timeout', 'sandbox_config_id', 'chat_parser_engine_rules', 'image_storage_provider',
  'web_search_provider_id', 'mcp_auth_wait_timeout', 'access_level',
  'attachment_ocr_max_pages', 'attachment_parse_wait_timeout_sec',
] as const

/** Do not replay old technical overrides when an existing agent is edited. */
export function managedAgentConfig<T extends object>(config: T, managed: boolean): T {
  if (!managed) return config
  const result: any = JSON.parse(JSON.stringify(config))
  for (const key of AGENT_RUNTIME_FIELDS) delete result[key]
  if (result.question_suggestions?.follow_ups) delete result.question_suggestions.follow_ups.model_id
  return result
}

/** KB embeddings/storage are server-owned and must never be inferred from browser caches. */
export function managedKnowledgePayload<T extends object>(payload: T, managed: boolean): T {
  if (!managed) return payload
  const result: any = JSON.parse(JSON.stringify(payload))
  for (const key of ['embedding_model_id', 'summary_model_id', 'vector_store_id', 'storage_backend_id',
    'storage_provider_config', 'storage_config', 'chunking_config', 'vlm_config', 'asr_config']) delete result[key]
  for (const key of ['wiki_config', 'auto_tag_config', 'profile_config']) {
    if (result[key]) {
      delete result[key].model_id
      delete result[key].synthesis_model_id
    }
  }
  return result
}
