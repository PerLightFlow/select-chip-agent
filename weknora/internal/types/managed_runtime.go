package types

import (
	"os"
	"strconv"
	"strings"
)

// ManagedRuntimeEnabled selects SOLEX's centrally managed infrastructure.
// The default remains the upstream workspace-managed deployment behavior.
func ManagedRuntimeEnabled() bool {
	enabled, _ := strconv.ParseBool(strings.TrimSpace(os.Getenv("SOLEX_MANAGED_RUNTIME")))
	return enabled
}

// ManagedRuntimeTenantID identifies the configuration workspace, never the
// execution/data workspace. Callers must not use it to broaden KB/chat access.
func ManagedRuntimeTenantID() uint64 {
	id, _ := strconv.ParseUint(strings.TrimSpace(os.Getenv("SOLEX_RUNTIME_TENANT_ID")), 10, 64)
	return id
}
