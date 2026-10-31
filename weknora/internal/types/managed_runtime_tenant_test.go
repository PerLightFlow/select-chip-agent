package types_test

import (
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
	"testing"
)

func TestManagedRuntimeInheritancePreservesWorkspaceIdentityAndDataBindings(t *testing.T) {
	storageID := "personal-storage"
	personal := &types.Tenant{ID: 99, Name: "personal", DefaultStorageBackendID: &storageID, MemoryConfig: &types.MemoryConfig{}, ChatHistoryConfig: &types.ChatHistoryConfig{}, Credentials: &types.CredentialsConfig{}}
	central := &types.Tenant{ID: 42, Name: "company", DefaultSettings: &types.DefaultSettings{ChatModelID: "shared"}, ParserEngineConfig: &types.ParserEngineConfig{}}
	effective := types.InheritManagedRuntimeConfig(personal, central)
	require.Equal(t, uint64(99), effective.ID)
	require.Equal(t, "personal", effective.Name)
	require.Same(t, personal.DefaultStorageBackendID, effective.DefaultStorageBackendID)
	require.Same(t, personal.MemoryConfig, effective.MemoryConfig)
	require.Same(t, personal.ChatHistoryConfig, effective.ChatHistoryConfig)
	require.Same(t, personal.Credentials, effective.Credentials)
	require.Equal(t, "shared", effective.DefaultSettings.ChatModelID)
	require.Same(t, central.ParserEngineConfig, effective.ParserEngineConfig)
	require.Nil(t, personal.DefaultSettings)
}
