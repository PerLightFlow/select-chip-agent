package middleware

import (
	"net/http"
	"strings"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/gin-gonic/gin"
)

// ManagedRuntime keeps personal workspace ownership separate from authority
// over company infrastructure. It also covers API keys and operations invoked
// through the HTTP dispatcher; hiding a setting in the SPA is not a guard.
func ManagedRuntime() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !types.ManagedRuntimeEnabled() || types.IsSystemAdminFromContext(c.Request.Context()) {
			c.Next()
			return
		}
		if managedRuntimeWrite(c.Request.Method, c.FullPath()) {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"success": false, "code": "RUNTIME_MANAGED_BY_SYSTEM",
				"message": "模型和运行配置由系统管理员统一管理",
			})
			return
		}
		c.Next()
	}
}

func managedRuntimeWrite(method, route string) bool {
	if method == http.MethodGet || method == http.MethodHead || method == http.MethodOptions {
		return false
	}
	// These POST/DELETE endpoints resolve metadata or the caller's own OAuth
	// authorization, not a shared server configuration.
	if route == "/api/v1/models/catalog/resolve" ||
		strings.HasPrefix(route, "/api/v1/mcp-services/:id/oauth/") ||
		route == "/api/v1/mcp-services/:id/metadata/refresh" {
		return false
	}
	for _, prefix := range []string{
		"/api/v1/models", "/api/v1/mcp-services", "/api/v1/web-search-providers",
		"/api/v1/vector-stores", "/api/v1/storage-backends", "/api/v1/sandbox-configs",
		"/api/v1/skills/catalog", "/api/v1/initialization", "/api/v1/datasource",
		"/api/v1/weknora-cloud", "/api/v1/tenants/kv",
	} {
		if route == prefix || strings.HasPrefix(route, prefix+"/") {
			return true
		}
	}
	switch route {
	case "/api/v1/knowledge-bases/:id/rebuild-index", "/api/v1/system/parser-engines/check", "/api/v1/system/docreader/reconnect", "/api/v1/system/storage-engine-check", "/api/v1/system/sandbox-check":
		return true
	}
	return false
}
