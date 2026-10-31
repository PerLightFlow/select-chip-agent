package types

// InheritManagedRuntimeConfig derives technical defaults without changing
// workspace identity, storage bindings, memory or any user-data ownership.
// Neither input is mutated. Repositories must not persist these derived fields.
func InheritManagedRuntimeConfig(tenant, central *Tenant) *Tenant {
	effective := *tenant
	effective.DefaultSettings = central.DefaultSettings
	effective.ContextConfig = central.ContextConfig
	effective.WebSearchConfig = central.WebSearchConfig
	effective.ParserEngineConfig = central.ParserEngineConfig
	effective.RetrievalConfig = central.RetrievalConfig
	return &effective
}
