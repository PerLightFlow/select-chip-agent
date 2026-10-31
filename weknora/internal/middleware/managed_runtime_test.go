package middleware

import (
	"context"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/gin-gonic/gin"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestManagedRuntimeWriteBoundary(t *testing.T) {
	for _, tc := range []struct {
		method, route string
		want          bool
	}{
		{"POST", "/api/v1/models", true},
		{"PUT", "/api/v1/models/:id/credentials", true},
		{"POST", "/api/v1/initialization/embedding/test", true},
		{"PUT", "/api/v1/tenants/kv/:key", true},
		{"POST", "/api/v1/mcp-services/:id/test", true},
		{"PUT", "/api/v1/sandbox-configs/workspace-policy", true},
		{"POST", "/api/v1/skills/catalog/:id/install", true},
		{"POST", "/api/v1/knowledge-bases/:id/rebuild-index", true},
		{"POST", "/api/v1/models/catalog/resolve", false},
		{"GET", "/api/v1/models", false},
		{"POST", "/api/v1/agents", false},
		{"POST", "/api/v1/knowledge-bases", false},
		{"POST", "/api/v1/knowledge-bases/:id/knowledge/file", false},
		{"POST", "/api/v1/automations", false},
		{"POST", "/api/v1/tenants", false},
		{"PUT", "/api/v1/auth/me/preferences", false},
		{"PUT", "/api/v1/me/env-vars", false},
		{"POST", "/api/v1/mcp-services/:id/oauth/authorize-url", false},
		{"DELETE", "/api/v1/mcp-services/:id/oauth/token", false},
	} {
		if got := managedRuntimeWrite(tc.method, tc.route); got != tc.want {
			t.Errorf("%s %s = %v, want %v", tc.method, tc.route, got, tc.want)
		}
	}
	if managedRuntimeWrite(http.MethodOptions, "/api/v1/models") {
		t.Fatal("preflight must remain available")
	}
}

func TestManagedRuntimeMiddlewareUsesSystemRoleNotWorkspaceOwnership(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name           string
		managed, admin bool
		want           int
	}{
		{"ordinary owner", true, false, 403}, {"system admin", true, true, 204}, {"upstream mode", false, false, 204},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.managed {
				t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
			} else {
				t.Setenv("SOLEX_MANAGED_RUNTIME", "false")
			}
			engine := gin.New()
			engine.Use(func(c *gin.Context) {
				c.Request = c.Request.WithContext(context.WithValue(c.Request.Context(), types.SystemAdminContextKey, tc.admin))
			})
			engine.Use(ManagedRuntime())
			engine.PUT("/api/v1/models/:id", func(c *gin.Context) { c.Status(204) })
			rec := httptest.NewRecorder()
			engine.ServeHTTP(rec, httptest.NewRequest("PUT", "/api/v1/models/shared-model", nil))
			if rec.Code != tc.want {
				t.Fatalf("status %d, want %d", rec.Code, tc.want)
			}
		})
	}
}
