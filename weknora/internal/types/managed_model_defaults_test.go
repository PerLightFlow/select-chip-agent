package types

import (
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestPickManagedDefaultModelRequiresAnExplicitSharedDefault(t *testing.T) {
	models := []*Model{
		{ID: "private-default", Type: ModelTypeKnowledgeQA, Status: ModelStatusActive, IsDefault: true},
		{ID: "shared-unselected", Type: ModelTypeKnowledgeQA, Status: ModelStatusActive, IsBuiltin: true},
		{ID: "inactive", Type: ModelTypeKnowledgeQA, Status: ModelStatusDownloadFailed, IsBuiltin: true, IsDefault: true},
	}
	assert.Nil(t, PickManagedDefaultModel(models, ModelTypeKnowledgeQA))
	models[1].DefaultFor = []string{string(ModelTypeKnowledgeQA)}
	assert.Same(t, models[1], PickManagedDefaultModel(models, ModelTypeKnowledgeQA))
	models[1].DefaultFor = nil
	models[1].IsDefault = true
	assert.Same(t, models[1], PickManagedDefaultModel(models, ModelTypeKnowledgeQA))
}
