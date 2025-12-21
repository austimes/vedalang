# Baseline Diagnostics - VedaLang Toolchain

Generated: 2024-12-21

## Overview

This document captures the baseline state of the VedaLang toolchain before schema evolution work begins.

## Toolchain Status

### Python Pipeline: ✅ WORKING

The Python components work end-to-end without exceptions:

| Tool | Status | Notes |
|------|--------|-------|
| `vedalang compile` | ✅ Pass | Compiles .veda.yaml → TableIR |
| `veda_emit_excel` | ✅ Pass | Emits TableIR → Excel files |
| `veda_check` | ✅ Pass | Orchestrates full pipeline |

### xl2times Validation: ❌ EXPECTED FAILURE

xl2times fails on minimal VedaLang output because **system tables are missing**.

**Error:**
```
ValueError: too few items in iterable (expected 1)
```

**Root cause:** xl2times requires `~BOOKREGIONS_MAP` table (and other system tables) that VedaLang doesn't yet emit.

## Test Results

```
44 tests passed (2024-12-21)

Key test files:
- test_vedalang_compiler.py - VedaLang → TableIR compilation
- test_veda_emit_excel.py - TableIR → Excel emission
- test_veda_check.py - Full pipeline orchestration
- test_xl2times_integration.py - xl2times with fixture models
```

## What VedaLang Can Currently Express

From `mini_plant.veda.yaml`:

```yaml
model:
  name: MiniModel
  regions: [REG1]
  
  commodities:
    - name: ELC
      type: energy
      unit: PJ
    - name: NG
      type: energy
      unit: PJ
  
  processes:
    - name: PP_CCGT
      sets: [ELE]
      activity_unit: PJ
      capacity_unit: GW
      inputs: [{commodity: NG, share: 1.0}]
      outputs: [{commodity: ELC, share: 1.0}]
      efficiency: 0.55
```

### Generated Tables

| Tag | Rows | Description |
|-----|------|-------------|
| `~FI_COMM` | 2 | Commodity definitions (ELC, NG) |
| `~FI_PROCESS` | 1 | Process definition (PP_CCGT) |
| `~FI_T` | 3 | Topology rows (inputs, outputs, efficiency) |

### Missing for xl2times

Required system tables not yet emitted:
- `~BOOKREGIONS_MAP` - Region mapping (required)
- `~ACTIVEPDEF` - Active PDEF setting
- `~CURRENCIES` - Currency definitions
- `~DEFUNITS` - Default units
- `~STARTYR` - Model start year
- `~TIMES` - Time periods

## Next Steps

1. **Phase 0.5**: Add system table emission to VedaLang compiler
2. **Phase 1**: Schema evolution for richer process/commodity types
3. **Phase 2**: Scenario support and parameter trajectories

## Reference: veda_check JSON Output

```json
{
  "success": false,
  "source": "vedalang/examples/mini_plant.veda.yaml",
  "tables": ["~FI_COMM", "~FI_PROCESS", "~FI_T"],
  "total_rows": 6,
  "warnings": 0,
  "errors": 0,
  "error_messages": []
}
```

Note: `success: false` because xl2times exit code ≠ 0 (crashes on missing system tables).
`errors: 0` because no diagnostics were produced before the crash.
