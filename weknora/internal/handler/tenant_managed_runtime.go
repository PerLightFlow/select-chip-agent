package handler

import (
	"context"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/gin-gonic/gin"
	"net/http"
)

// Called only for configuration endpoints. Never changes TenantIDContextKey,
// session identity, or the tenant used by document and chat operations.
func (h *TenantHandler) useManagedRuntimeConfigContext(c *gin.Context) bool {
	if !types.ManagedRuntimeEnabled() {
		return true
	}
	switch c.Param("key") {
	case "default-settings", "web-search-config", "parser-engine-config", "retrieval-config":
	default:
		return true
	}
	ctx := c.Request.Context()
	if c.Request.Method != http.MethodGet && !types.IsSystemAdminFromContext(ctx) {
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"success": false, "message": "配置由系统管理员管理"})
		return false
	}
	tenant, err := h.service.GetTenantByID(ctx, types.ManagedRuntimeTenantID())
	if err != nil || tenant == nil {
		c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "系统运行配置尚未就绪，请联系管理员"})
		return false
	}
	c.Request = c.Request.WithContext(context.WithValue(ctx, types.TenantInfoContextKey, tenant))
	return true
}
