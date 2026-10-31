package repository

import (
	"context"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
	"testing"
)

func TestManagedSearchSharesOnlyConfigurationAndRejectsOrdinaryWrites(t *testing.T) {
	db, repo := newWebSearchProviderTestRepository(t)
	ctx := context.WithValue(context.Background(), types.TenantIDContextKey, uint64(99))
	central := newDuckDuckGoProvider("company", true)
	require.NoError(t, repo.Create(ctx, central))
	private := newDuckDuckGoProvider("private", false)
	private.TenantID = 99
	require.NoError(t, db.Create(private).Error)
	t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
	t.Setenv("SOLEX_RUNTIME_TENANT_ID", "42")
	got, err := repo.GetDefault(ctx, 99)
	require.NoError(t, err)
	require.Equal(t, central.ID, got.ID)
	list, err := repo.List(ctx, 99)
	require.NoError(t, err)
	require.Len(t, list, 1)
	hidden, err := repo.GetByID(ctx, 99, private.ID)
	require.NoError(t, err)
	require.Nil(t, hidden)
	require.Error(t, repo.Delete(ctx, 99, central.ID))
	require.Error(t, repo.Create(ctx, newDuckDuckGoProvider("forbidden", false)))
	admin := context.WithValue(ctx, types.SystemAdminContextKey, true)
	replacement := newDuckDuckGoProvider("replacement", true)
	replacement.TenantID = 99
	require.NoError(t, repo.Create(admin, replacement))
	got, err = repo.GetDefault(ctx, 99)
	require.NoError(t, err)
	require.Equal(t, replacement.ID, got.ID)
	id, _ := types.TenantIDFromContext(ctx)
	require.Equal(t, uint64(99), id)
}

func TestManagedTenantWorkerReadsDefaultsWithoutPersistingOverlays(t *testing.T) {
	db := setupTestDB(t)
	ctx := context.Background()
	center := &types.Tenant{ID: 42, Name: "company", DefaultSettings: &types.DefaultSettings{ChatModelID: "shared"}}
	personal := &types.Tenant{ID: 99, Name: "personal", DefaultSettings: &types.DefaultSettings{ChatModelID: "old-private"}}
	require.NoError(t, db.Create(center).Error)
	require.NoError(t, db.Create(personal).Error)
	repo := NewTenantRepository(db)
	t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
	t.Setenv("SOLEX_RUNTIME_TENANT_ID", "42")
	effective, err := repo.GetTenantByID(ctx, 99)
	require.NoError(t, err)
	require.Equal(t, uint64(99), effective.ID)
	require.Equal(t, "shared", effective.DefaultSettings.ChatModelID)
	effective.Description = "keep this personal change"
	require.NoError(t, repo.UpdateTenant(ctx, effective))
	var raw types.Tenant
	require.NoError(t, db.First(&raw, 99).Error)
	require.Equal(t, "old-private", raw.DefaultSettings.ChatModelID)
	require.Equal(t, effective.Description, raw.Description)
	batch, err := repo.GetTenantsByIDs(ctx, []uint64{42, 99})
	require.NoError(t, err)
	require.Equal(t, "shared", batch[99].DefaultSettings.ChatModelID)
	require.Equal(t, uint64(99), batch[99].ID)
}

func TestManagedMCPRuntimeCannotUseAnOldPrivateConnection(t *testing.T) {
	db := setupTestDB(t)
	require.NoError(t, db.AutoMigrate(&types.MCPService{}))
	ctx := context.Background()
	for _, svc := range []*types.MCPService{
		{ID: "shared", TenantID: 42, Name: "company", IsBuiltin: true, Enabled: true},
		{ID: "private", TenantID: 99, Name: "private", Enabled: true},
	} {
		require.NoError(t, db.Create(svc).Error)
	}
	t.Setenv("SOLEX_MANAGED_RUNTIME", "true")
	repo := NewMCPServiceRepository(db)
	private, err := repo.GetByID(ctx, 99, "private")
	require.NoError(t, err)
	require.Nil(t, private)
	services, err := repo.ListEnabled(ctx, 99)
	require.NoError(t, err)
	require.Len(t, services, 1)
	require.Equal(t, "shared", services[0].ID)
	selected, err := repo.ListByIDs(ctx, 99, []string{"private", "shared"})
	require.NoError(t, err)
	require.Len(t, selected, 1)
	require.Error(t, repo.Delete(ctx, 42, "shared"))
	admin := context.WithValue(ctx, types.SystemAdminContextKey, true)
	require.NoError(t, repo.Delete(admin, 42, "shared"))
}
