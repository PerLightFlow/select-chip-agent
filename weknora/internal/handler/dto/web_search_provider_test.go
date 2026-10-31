package dto

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/assert"
)

func TestWebSearchProviderResponse_OmitsSecrets(t *testing.T) {
	e := &types.WebSearchProviderEntity{
		ID:       "wsp-1",
		Name:     "bing prod",
		Provider: types.WebSearchProviderTypeBing,
		Parameters: types.WebSearchProviderParameters{
			APIKey:   "bing-secret-do-not-leak",
			EngineID: "engine-public-id",
			BaseURL:  "https://example.com",
		},
	}
	body, err := json.Marshal(NewWebSearchProviderResponse(adminContext(), e))
	assert.NoError(t, err)
	s := string(body)
	assert.NotContains(t, s, "bing-secret-do-not-leak")
	// Parameters sub-object must contain no secret keys.
	var raw map[string]json.RawMessage
	assert.NoError(t, json.Unmarshal(body, &raw))
	assert.NotContains(t, string(raw["parameters"]), `"api_key"`)
	// Credential metadata map exposes booleans only.
	assert.Contains(t, s, `"credentials"`)
	assert.Contains(t, s, `"api_key":{"configured":true}`)
	// Non-secret fields pass through.
	assert.Contains(t, s, "engine-public-id")
	assert.Contains(t, s, "example.com")
}

func TestWebSearchProviderResponse_ViewerStripsIntegrationDetail(t *testing.T) {
	e := &types.WebSearchProviderEntity{
		ID: "wsp-2",
		Parameters: types.WebSearchProviderParameters{
			ProxyURL:    "http://proxy:8080",
			ExtraConfig: map[string]string{"token": "secret"},
		},
	}
	resp := NewWebSearchProviderResponse(viewerContext(), e)
	assert.Empty(t, resp.Parameters.ProxyURL)
	assert.Nil(t, resp.Parameters.ExtraConfig)
}

func TestWebSearchProviderResponse_NilSafe(t *testing.T) {
	assert.Nil(t, NewWebSearchProviderResponse(adminContext(), nil))
	assert.Equal(t, []*WebSearchProviderResponse{}, NewWebSearchProviderResponses(adminContext(), nil))
}

func TestWebSearchProviderResponse_ManagedOwnerCannotReadCentralCredentials(t *testing.T) {
	t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
	e := &types.WebSearchProviderEntity{
		ID: "central-search", TenantID: 42,
		Parameters: types.WebSearchProviderParameters{
			APIKey:      "never-return-api-key",
			ProxyURL:    "http://proxy-user:proxy-password@proxy.example.com:8080",
			ExtraConfig: map[string]string{"token": "provider-private-token"},
		},
	}
	resp := NewWebSearchProviderResponse(ownerContext(), e)
	assert.Empty(t, resp.Parameters.ProxyURL)
	assert.Nil(t, resp.Parameters.ExtraConfig)
	assert.True(t, resp.Credentials["api_key"].Configured)
	body, err := json.Marshal(resp)
	assert.NoError(t, err)
	assert.NotContains(t, string(body), "proxy-password")
	assert.NotContains(t, string(body), "provider-private-token")
	assert.NotContains(t, string(body), "never-return-api-key")
	// Redacting the public response must not corrupt runtime configuration.
	assert.Equal(t, "provider-private-token", e.Parameters.ExtraConfig["token"])

	admin := context.WithValue(ownerContext(), types.SystemAdminContextKey, true)
	adminResponse := NewWebSearchProviderResponse(admin, e)
	assert.Equal(t, e.Parameters.ProxyURL, adminResponse.Parameters.ProxyURL)
	assert.Equal(t, e.Parameters.ExtraConfig, adminResponse.Parameters.ExtraConfig)
}

func TestWebSearchProviderResponse_UnmanagedOwnerRetainsWorkspaceDetail(t *testing.T) {
	t.Setenv("SOLEX_MANAGED_RUNTIME", "false")
	e := &types.WebSearchProviderEntity{
		Parameters: types.WebSearchProviderParameters{
			ProxyURL: "http://own-proxy.example.com:8080", ExtraConfig: map[string]string{"region": "local"},
		},
	}
	resp := NewWebSearchProviderResponse(ownerContext(), e)
	assert.Equal(t, e.Parameters.ProxyURL, resp.Parameters.ProxyURL)
	assert.Equal(t, e.Parameters.ExtraConfig, resp.Parameters.ExtraConfig)
}
