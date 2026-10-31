package types

import "slices"

// PickManagedDefaultModel only considers an explicit, active platform model
// default. It deliberately avoids PickDefaultModel's first-available fallback.
func PickManagedDefaultModel(models []*Model, kind ModelType) *Model {
	var fallback *Model
	for _, model := range models {
		if model == nil || !model.IsBuiltin || model.Status != ModelStatusActive || !model.SupportsType(kind) {
			continue
		}
		if slices.Contains(model.DefaultFor, string(kind)) {
			return model
		}
		if fallback == nil && model.IsDefault && model.Type == kind {
			fallback = model
		}
	}
	return fallback
}
