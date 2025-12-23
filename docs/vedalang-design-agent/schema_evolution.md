# VedaLang Schema Evolution Policy

This document defines the rules for safely evolving `vedalang.schema.json` without breaking existing VedaLang source files.

## Guiding Principle

**Backward compatibility is mandatory.** Any valid VedaLang file that worked before a schema change must continue to work after.

## Allowed Changes

These changes are safe and can be made freely:

| Change Type | Example | Why Safe |
|-------------|---------|----------|
| Add optional properties | Add `vintage` to process | Existing files don't use it, still valid |
| Add new `$defs` types | Add `trade_link` definition | No existing usage to break |
| Widen enum values | Add `"financial"` to commodity types | Existing values still valid |
| Increase maximum constraints | Change `maxItems: 10` → `maxItems: 20` | Existing files still within limits |
| Add default values | Add `default: "PJ"` to unit field | Makes optional fields more convenient |

## Disallowed Changes

These changes break backward compatibility and are **forbidden**:

| Change Type | Example | Why Dangerous |
|-------------|---------|---------------|
| Remove required properties | Remove `name` from process | Existing files now invalid |
| Rename properties | `efficiency` → `eff` | Existing files use old name |
| Narrow enum values | Remove `"emission"` from commodity types | Existing files using it break |
| Decrease maximum constraints | Change `maxItems: 20` → `maxItems: 10` | Files exceeding new limit break |
| Change property types | `efficiency: number` → `efficiency: string` | Type mismatch in existing files |
| Make optional properties required | Make `description` required | Existing files missing it break |

## Process for Schema Changes

1. **Propose change** - Describe what you want to add/modify
2. **Check compatibility** - Verify change is in "Allowed" category
3. **Update schema** - Modify `vedalang.schema.json`
4. **Update examples** - Ensure `vedalang/examples/` files still validate
5. **Update tests** - Add tests for new features
6. **Update compiler** - Handle new schema elements
7. **Run compatibility test** - `uv run pytest tests/test_schema_compatibility.py`

## Baseline Required Fields

These fields are **locked** and must never be removed:

### Model Level
- `model` (root object, required)
- `model.name` (string, required)
- `model.regions` (array, required)
- `model.commodities` (array, required)
- `model.processes` (array, required)

### Commodity Definition
- `commodity.name` (string, required)
- `commodity.type` (enum, required)

### Process Definition
- `process.name` (string, required)
- `process.sets` (array, required)

### Flow Definition
- `flow.commodity` (string, required)

### Scenario Definition
- `scenario.name` (string, required)
- `scenario.type` (enum, required)

## Baseline Enum Values

These enum values are **locked** and must never be removed:

### Commodity Types
- `energy`
- `material`
- `emission`
- `demand`

### Scenario Types
- `commodity_price`

## Deprecation Process

If a breaking change is truly necessary:

1. **Add new property** alongside old one
2. **Mark old property deprecated** in description
3. **Support both** in compiler for at least 2 versions
4. **Warn on old usage** via compiler diagnostics
5. **Remove after deprecation period** (minimum 2 releases)

## Automated Enforcement

The test suite includes `tests/test_schema_compatibility.py` which:

- Verifies all baseline required fields exist
- Verifies all baseline enum values exist
- Fails CI if breaking changes are introduced

Run before committing schema changes:
```bash
uv run pytest tests/test_schema_compatibility.py -v
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2024-12 | Initial schema: commodities, processes, flows |
| v1.1 | 2024-12 | Added `scenarios` for TFM parameters (DC4) |
