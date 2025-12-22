# VedaLang Project Status

**Last updated:** 2025-12-23

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. **Primitives Exploration Phase is complete** — all schema extensions implemented. Now entering **MiniSystem Stress Test phase**.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ 162+ tests passing |
| Primitives Exploration | ✅ Complete |
| Schema Extensions | ✅ All implemented |
| **MiniSystem Stress Test** | 🔄 **ACTIVE** |

---

## Current Phase: MiniSystem Stress Test

**Epic:** `vedalang-93s` — Phase 2: MiniSystem Stress Test

### Open Tasks

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-5dw` | P1 | Design MiniSystem model specification | 🔄 Open |
| `vedalang-scv` | P1 | Implement MiniSystem model in VedaLang | 🔄 Open |
| `vedalang-4t8` | P1 | Wire MiniSystem as golden CI test | 🔄 Open |
| `vedalang-1lb` | P2 | Ergonomic improvements based on authoring friction | 🔄 Open |
| `vedalang-6qs` | P2 | Add time-varying process attributes (time_series) | 🔄 Open |

### Future Work (P3)

| Issue | Description |
|-------|-------------|
| `vedalang-jis` | Storage and flexibility primitives |
| `vedalang-9xy` | Scenario composition and variants |
| `vedalang-a9m` | Units and dimension checking system |

---

## Completed Work Summary

**53 issues closed** across all phases.

### Phase 0: Toolchain Validation ✅
- `vedalang compile` works
- `veda_emit_excel` emits valid Excel
- `veda_check` orchestrates pipeline
- xl2times emits structured diagnostics

### Phase 1: TableIR Experimentation ✅
- Design challenges DC1-DC5 complete
- Golden fixture regression tests
- Schema evolution policy
- Failure tracking infrastructure

### Phase 2: Primitives Exploration ✅

All 10 energy system primitives explored and implemented:

| Primitive | Outcome | Implementation |
|-----------|---------|----------------|
| Thermal generation | Pattern | DC1, DC2 |
| Renewable generation | Pattern | DC2 |
| Emissions & pricing | Pattern | DC3, DC4 |
| CHP | Pattern | Multi-output works |
| Storage | Pattern | Same-commodity I/O |
| Transmission | Pattern | Voltage-level commodities |
| Demand trajectories | Schema extension | `demand_projection` |
| Fuel supply / Costs | Schema extension | `invcost`, `fixom`, `varom`, `life`, `cost` |
| Capacity bounds | Schema extension | `activity_bound`, `cap_bound`, `ncap_bound` |
| Timeslices | Schema extension | `timeslices` section |
| Trade | Schema extension | `trade_links` array |
| User constraints | Schema extension | `emission_cap`, `activity_share` |

---

## VedaLang Capabilities

### What VedaLang Can Express

| Concept | Schema Support |
|---------|----------------|
| Single/multi-region models | ✅ |
| Energy/emission/demand commodities | ✅ |
| Thermal & renewable plants | ✅ |
| CHP (multi-output) | ✅ |
| Storage (same-commodity I/O) | ✅ |
| Transmission (voltage levels) | ✅ |
| Process efficiency | ✅ |
| Process costs | ✅ |
| Capacity/activity bounds | ✅ |
| Emission factors | ✅ |
| CO2 price scenarios | ✅ |
| Demand projections | ✅ |
| Timeslices | ✅ |
| Inter-regional trade | ✅ |
| User constraints | ✅ |
| Trade link efficiency (IRE_FLO) | ✅ |

### Not Yet Implemented

| Concept | Issue | Priority |
|---------|-------|----------|
| Time-varying attributes | `vedalang-6qs` | P2 |
| Storage primitives (enhanced) | `vedalang-jis` | P3 |
| Scenario composition | `vedalang-9xy` | P3 |
| Units/dimension checking | `vedalang-a9m` | P3 |
| Vintage/age tracking | — | Future |
| Growth rate constraints | — | Future |

---

## Commands Reference

```bash
# Validate a VedaLang model
uv run veda_check model.veda.yaml --from-vedalang --json

# Compile to TableIR only
uv run vedalang compile model.veda.yaml --tableir output.yaml

# Emit Excel from TableIR
uv run veda_emit_excel tableir.yaml --out output_dir/

# Run all tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .

# Check issue status
bd list --all | grep " open "
```

---

## Keeping This Document Updated

**This document should be updated when:**
1. Issues are closed → move from "Open" to completed section
2. New issues are created → add to appropriate section
3. Phase transitions occur → update "Current Phase"

**Quick sync command:**
```bash
# Show current open issues
bd list --all | grep " open "

# Count closed issues
bd list --all | grep " closed " | wc -l
```

---

## Repository Structure

```
veda-devtools/
├── AGENTS.md                 # Agent instructions
├── docs/
│   ├── STATUS.md             # This file (living status)
│   └── ...
├── experiments/              # Primitive exploration results
├── vedalang/
│   ├── schema/               # JSON Schema (complete)
│   ├── compiler/             # Compiler (complete)
│   └── examples/             # 10+ example files
├── tools/
├── rules/
├── tests/                    # 162+ tests
├── fixtures/
└── xl2times/                 # Submodule (hardened)
```
