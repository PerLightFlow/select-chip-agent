package service

import (
	"context"
	"reflect"
	"strings"

	apperrors "github.com/Tencent/WeKnora/internal/errors"
	"github.com/Tencent/WeKnora/internal/types"
)

func (s *knowledgeBaseService) applyManagedKnowledgeBaseModels(ctx context.Context, kb *types.KnowledgeBase) error {
	if !managedModelRestricted(ctx) {
		return nil
	}
	// Runtime connections are deployment-owned, including legacy inline storage.
	if kb.VectorStoreID != nil && strings.TrimSpace(*kb.VectorStoreID) != "" {
		return apperrors.NewForbiddenError("向量存储由系统管理员统一配置")
	}
	if kb.StorageBackendID != nil && strings.TrimSpace(*kb.StorageBackendID) != "" {
		tenant, _ := types.TenantInfoFromContext(ctx)
		if tenant == nil || tenant.DefaultStorageBackendID == nil || *kb.StorageBackendID != *tenant.DefaultStorageBackendID {
			return apperrors.NewForbiddenError("文件存储由系统管理员统一配置")
		}
	}
	if kb.StorageConfig != (types.StorageConfig{}) {
		return apperrors.NewForbiddenError("不能提交独立文件存储连接")
	}
	kb.VectorStoreID = nil
	kb.StorageProviderConfig = nil
	kb.ChunkingConfig.ParserEngineRules = nil
	var err error
	kb.SummaryModelID, err = managedModelBinding(ctx, s.modelService, kb.SummaryModelID, types.ModelTypeKnowledgeQA)
	if err != nil {
		return err
	}
	if kb.IsVectorEnabled() || kb.EmbeddingModelID != "" {
		kb.EmbeddingModelID, err = managedModelBinding(ctx, s.modelService, kb.EmbeddingModelID, types.ModelTypeEmbedding)
		if err != nil {
			return err
		}
	}
	if kb.WikiConfig != nil {
		kb.WikiConfig.SynthesisModelID = ""
	}
	if kb.ProfileConfig != nil {
		kb.ProfileConfig.ModelID = ""
	}
	if kb.AutoTagConfig != nil {
		kb.AutoTagConfig.ModelID = ""
	}
	if kb.ImageProcessingConfig.ModelID != "" {
		kb.ImageProcessingConfig.ModelID, err = managedModelBinding(ctx, s.modelService, kb.ImageProcessingConfig.ModelID, types.ModelTypeVLLM)
		if err != nil {
			return err
		}
	}
	if err := s.normalizeManagedVLM(ctx, &kb.VLMConfig, nil); err != nil {
		return err
	}
	if kb.ASRConfig.Enabled {
		kb.ASRConfig.ModelID, err = managedModelBinding(ctx, s.modelService, kb.ASRConfig.ModelID, types.ModelTypeASR)
		if err != nil {
			return err
		}
	}
	return nil
}

// A basic metadata edit never changes a populated index's embedding model.
// Even after the central default changes, echoing or omitting the old binding
// is safe; selecting a new vector space remains an explicit admin operation.
func (s *knowledgeBaseService) normalizeManagedKnowledgeBaseUpdate(ctx context.Context, kb *types.KnowledgeBase, cfg *types.KnowledgeBaseConfig, vlm *types.VLMConfig) error {
	if !managedModelRestricted(ctx) {
		return nil
	}
	if cfg != nil {
		if len(cfg.ChunkingConfig.ParserEngineRules) > 0 && !reflect.DeepEqual(cfg.ChunkingConfig.ParserEngineRules, kb.ChunkingConfig.ParserEngineRules) {
			return apperrors.NewForbiddenError("解析引擎由系统管理员统一配置")
		}
		cfg.ChunkingConfig.ParserEngineRules = kb.ChunkingConfig.ParserEngineRules
		if cfg.StorageBackendID != nil {
			next := strings.TrimSpace(*cfg.StorageBackendID)
			if next == "" || (kb.StorageBackendID != nil && next == *kb.StorageBackendID) {
				cfg.StorageBackendID = nil
			} else {
				return apperrors.NewForbiddenError("文件存储由系统管理员统一配置")
			}
		}
		if cfg.EmbeddingModelID != nil {
			next := strings.TrimSpace(*cfg.EmbeddingModelID)
			if next == "" || next == kb.EmbeddingModelID {
				cfg.EmbeddingModelID = nil
			} else {
				return apperrors.NewForbiddenError("Embedding 模型由系统管理员统一管理；已有资料的索引不能自动切换")
			}
		}
		if cfg.SummaryModelID != nil {
			next := strings.TrimSpace(*cfg.SummaryModelID)
			if next == "" || next == kb.SummaryModelID {
				cfg.SummaryModelID = nil
			} else {
				return apperrors.NewForbiddenError("知识库生成模型由系统管理员统一管理")
			}
		}
		if cfg.WikiConfig != nil {
			cfg.WikiConfig.SynthesisModelID = ""
			if kb.WikiConfig != nil {
				cfg.WikiConfig.SynthesisModelID = kb.WikiConfig.SynthesisModelID
			}
		}
		if cfg.ProfileConfig != nil {
			cfg.ProfileConfig.ModelID = ""
			if kb.ProfileConfig != nil {
				cfg.ProfileConfig.ModelID = kb.ProfileConfig.ModelID
			}
		}
		if cfg.AutoTagConfig != nil {
			cfg.AutoTagConfig.ModelID = ""
			if kb.AutoTagConfig != nil {
				cfg.AutoTagConfig.ModelID = kb.AutoTagConfig.ModelID
			}
		}
		if cfg.ImageProcessingConfig != nil {
			cfg.ImageProcessingConfig.ModelID = kb.ImageProcessingConfig.ModelID
		}
		if cfg.ASRConfig != nil && cfg.ASRConfig.Enabled {
			if kb.ASRConfig.ModelID != "" {
				cfg.ASRConfig.ModelID = kb.ASRConfig.ModelID
			} else {
				id, err := managedModelBinding(ctx, s.modelService, cfg.ASRConfig.ModelID, types.ModelTypeASR)
				if err != nil {
					return err
				}
				cfg.ASRConfig.ModelID = id
			}
		}
	}
	return s.normalizeManagedVLM(ctx, vlm, &kb.VLMConfig)
}

func (s *knowledgeBaseService) normalizeManagedVLM(ctx context.Context, next, current *types.VLMConfig) error {
	if next == nil {
		return nil
	}
	// Legacy inline endpoint credentials are a second model connection surface.
	if next.BaseURL != "" || next.APIKey != "" || next.ModelName != "" || next.InterfaceType != "" {
		return apperrors.NewForbiddenError("视觉模型连接由系统管理员统一配置")
	}
	if !next.Enabled {
		next.ModelID = ""
		return nil
	}
	if current != nil && current.ModelID != "" {
		next.ModelID = current.ModelID
		return nil
	}
	id, err := managedModelBinding(ctx, s.modelService, next.ModelID, types.ModelTypeVLLM)
	if err != nil {
		return err
	}
	next.ModelID = id
	return nil
}
