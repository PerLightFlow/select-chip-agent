/**
 * Presentation-only aliases for server-owned built-ins. IDs, prompts, tool names,
 * and user-authored records deliberately retain their original values.
 */
const BUILTIN_AGENT_IDS = new Set([
  'builtin-quick-answer',
  'builtin-smart-reasoning',
  'builtin-deep-researcher',
  'builtin-data-analyst',
  'builtin-knowledge-graph-expert',
  'builtin-document-assistant',
  'builtin-wiki-researcher',
  'builtin-wiki-fixer',
  'builtin-skill-installer',
  'builtin-weknora-assistant',
])

export function builtinAgentDisplayText(id: string, text: string): string {
  return BUILTIN_AGENT_IDS.has(id) ? text.replace(/\bweknora\b/gi, 'SOLEX') : text
}

interface AgentDisplayFields {
  id: string
  name: string
  description?: string
}

export function brandBuiltinAgent<T extends AgentDisplayFields>(agent: T): T {
  if (!BUILTIN_AGENT_IDS.has(agent.id)) return agent
  const name = builtinAgentDisplayText(agent.id, agent.name)
  const description = agent.description == null
    ? agent.description
    : builtinAgentDisplayText(agent.id, agent.description)
  if (name === agent.name && description === agent.description) return agent
  return { ...agent, name, description }
}
