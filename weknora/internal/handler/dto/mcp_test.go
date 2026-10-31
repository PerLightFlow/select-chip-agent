package dto

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/assert"
)

// The most important guarantee of the DTO layer is structural: the serialized
// response body must NEVER contain api_key or token under any condition,
// regardless of the underlying entity's state. We assert this via the
// serialized JSON (not just struct shape) because reflection-based
// custom-marshalers anywhere downstream could otherwise reintroduce a leak.

func TestMCPServiceResponse_OmitsSecrets(t *testing.T) {
	svc := &types.MCPService{
		ID:   "svc-1",
		Name: "svc",
		AuthConfig: &types.MCPAuthConfig{
			APIKey:        "sk-real-api-key-do-not-leak",
			Token:         "tok-real-bearer-token-do-not-leak",
			CustomHeaders: map[string]string{"X-Trace": "abc"},
		},
	}
	body, err := json.Marshal(NewMCPServiceResponse(adminContext(), svc))
	assert.NoError(t, err)
	s := string(body)
	assert.NotContains(t, s, "sk-real-api-key-do-not-leak",
		"raw api_key must never appear in MCPServiceResponse")
	assert.NotContains(t, s, "tok-real-bearer-token-do-not-leak",
		"raw token must never appear in MCPServiceResponse")
	// auth_config no longer has api_key/token fields (only custom_headers
	// survived). Verify the auth_config sub-object contains no secret keys.
	var raw map[string]json.RawMessage
	assert.NoError(t, json.Unmarshal(body, &raw))
	if ac, ok := raw["auth_config"]; ok {
		acStr := string(ac)
		assert.NotContains(t, acStr, `"api_key"`)
		assert.NotContains(t, acStr, `"token"`)
	}
	// The new credentials map exposes "configured?" booleans by design
	// (replaces the standalone GET /credentials endpoint). Verify the
	// values are booleans, not strings.
	assert.Contains(t, s, `"credentials"`)
	assert.Contains(t, s, `"api_key":{"configured":true}`)
	assert.Contains(t, s, `"token":{"configured":true}`)
	// CustomHeaders is structural metadata and SHOULD pass through.
	assert.Contains(t, s, `"custom_headers"`)
	assert.Contains(t, s, `"X-Trace"`)
}

func TestMCPServiceResponse_BuiltinStripsTenantConfig(t *testing.T) {
	url := "https://tenant-private.example.com"
	svc := &types.MCPService{
		ID:        "builtin-1",
		IsBuiltin: true,
		URL:       &url,
		Headers:   types.MCPHeaders{"X-Tenant-Secret": "shhh"},
		AuthConfig: &types.MCPAuthConfig{
			APIKey: "should-not-leak-via-builtin",
		},
	}
	resp := NewMCPServiceResponse(adminContext(), svc)
	assert.Nil(t, resp.URL, "builtin must not leak per-tenant URL")
	assert.Nil(t, resp.Headers, "builtin must not leak per-tenant headers")
	assert.Nil(t, resp.AuthConfig, "builtin must not leak auth config")

	body, _ := json.Marshal(resp)
	assert.False(t, strings.Contains(string(body), "should-not-leak-via-builtin"))
	assert.False(t, strings.Contains(string(body), "X-Tenant-Secret"))
}

func TestMCPServiceResponse_ViewerStripsIntegrationDetail(t *testing.T) {
	url := "https://tenant-private.example.com"
	svc := &types.MCPService{
		ID:      "svc-2",
		URL:     &url,
		Headers: types.MCPHeaders{"Authorization": "Bearer secret"},
		EnvVars: types.MCPEnvVars{"TOKEN": "secret"},
		StdioConfig: &types.MCPStdioConfig{
			Command: "npx",
			Args:    []string{"-y", "mcp-server"},
		},
		AdvancedConfig: &types.MCPAdvancedConfig{},
		AuthConfig: &types.MCPAuthConfig{
			CustomHeaders: map[string]string{"X-Auth": "secret"},
		},
	}
	resp := NewMCPServiceResponse(viewerContext(), svc)
	assert.Nil(t, resp.URL)
	assert.Nil(t, resp.Headers)
	assert.Nil(t, resp.EnvVars)
	assert.Nil(t, resp.StdioConfig)
	assert.Nil(t, resp.AdvancedConfig)
	assert.NotNil(t, resp.AuthConfig)
	assert.Nil(t, resp.AuthConfig.CustomHeaders)
}

func TestMCPServiceResponse_NilSafe(t *testing.T) {
	assert.Nil(t, NewMCPServiceResponse(adminContext(), nil))
	assert.Equal(t, []*MCPServiceResponse{}, NewMCPServiceResponses(adminContext(), nil))
}

func TestAttachMCPCatalogs_MarksStaleWithoutCopyingTools(t *testing.T) {
	svc := &types.MCPService{ID: "svc-1", TransportType: types.MCPTransportSSE}
	resp := NewMCPServiceResponses(adminContext(), []*types.MCPService{svc})
	AttachMCPCatalogs(resp, []*types.MCPService{svc}, map[string]*types.MCPMetadataSummary{
		"svc-1": {ServiceID: "svc-1", ToolCount: 3, ConfigFingerprint: "old"},
	})
	require := assert.New(t)
	require.NotNil(resp[0].Catalog)
	require.Equal(3, resp[0].Catalog.ToolCount)
	require.True(resp[0].Catalog.Stale)
	body, err := json.Marshal(resp[0])
	require.NoError(err)
	require.NotContains(string(body), `"tools"`)
	require.Contains(string(body), `"tool_count":3`)
}

func TestMCPServiceResponse_EchoesClientIDButNotItsSecret(t *testing.T) {
	svc := &types.MCPService{
		ID:   "svc-1",
		Name: "svc",
		AuthConfig: &types.MCPAuthConfig{
			AuthType:     types.MCPAuthOAuth,
			ClientID:     "pre-registered",
			ClientSecret: "client-secret-do-not-leak",
		},
	}
	body, err := json.Marshal(NewMCPServiceResponse(adminContext(), svc))
	assert.NoError(t, err)
	s := string(body)
	assert.NotContains(t, s, "client-secret-do-not-leak")
	assert.Contains(t, s, `"client_id":"pre-registered"`)
	assert.Contains(t, s, `"client_secret":{"configured":true}`)
}

func TestMCPServiceResponse_ManagedSystemAdminCanEditBuiltin(t *testing.T) {
	t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
	// System administration does not require Admin membership of the active
	// workspace. Configuration remains visible when that membership is Viewer.
	ctx := context.WithValue(viewerContext(), types.SystemAdminContextKey, true)
	url := "https://shared-provider.example.com/mcp"
	svc := &types.MCPService{
		ID:        "builtin-managed",
		IsBuiltin: true,
		URL:       &url,
		Headers:   types.MCPHeaders{"X-Route": "shared"},
		AuthConfig: &types.MCPAuthConfig{
			AuthType:     types.MCPAuthOAuth,
			ClientID:     "registered-client",
			APIKey:       "never-return-api-key",
			Token:        "never-return-token",
			ClientSecret: "never-return-client-secret",
		},
	}
	resp := NewMCPServiceResponse(ctx, svc)
	assert.Equal(t, &url, resp.URL)
	assert.Equal(t, svc.Headers, resp.Headers)
	if assert.NotNil(t, resp.AuthConfig) {
		assert.Equal(t, "registered-client", resp.AuthConfig.ClientID)
		assert.Equal(t, types.MCPAuthOAuth, resp.AuthConfig.AuthType)
	}
	assert.True(t, resp.Credentials["api_key"].Configured)
	assert.True(t, resp.Credentials["token"].Configured)
	assert.True(t, resp.Credentials["client_secret"].Configured)
	body, err := json.Marshal(resp)
	assert.NoError(t, err)
	assert.NotContains(t, string(body), "never-return-")

	// An ordinary personal-workspace Owner still only receives the catalog.
	ordinary := NewMCPServiceResponse(ownerContext(), svc)
	assert.Nil(t, ordinary.URL)
	assert.Nil(t, ordinary.Headers)
	assert.Nil(t, ordinary.AuthConfig)
	assert.Nil(t, ordinary.Credentials)
}

func TestMCPServiceResponse_UnmanagedBuiltinRetainsOriginalRedaction(t *testing.T) {
	t.Setenv("SOLEX_MANAGED_RUNTIME", "false")
	ctx := context.WithValue(viewerContext(), types.SystemAdminContextKey, true)
	url := "https://shared-provider.example.com/mcp"
	resp := NewMCPServiceResponse(ctx, &types.MCPService{
		IsBuiltin: true, URL: &url,
		AuthConfig: &types.MCPAuthConfig{APIKey: "never-return-api-key"},
	})
	assert.Nil(t, resp.URL)
	assert.Nil(t, resp.AuthConfig)
	assert.Nil(t, resp.Credentials)
}
