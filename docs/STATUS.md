# VedaLang Project Status

**Last updated:** 2025-12-21

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. The toolchain is complete and we are now in the **Primitives Exploration Phase**.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ 134 tests passing |
| Documentation | ✅ Complete |
| Exploration infrastructure | ✅ Ready |

---

## Current Phase: Primitives Exploration

**Epic:** `vedalang-fq8`

The infrastructure is complete for an AI agent to autonomously explore energy system primitives and extend VedaLang. See [docs/exploration_prompt.md](exploration_prompt.md) for the full exploration protocol.

### Primitives Exploration Roadmap

| Primitive | Issue | Status | Notes |
|-----------|-------|--------|-------|
| Thermal generation | - | ✅ Complete | DC1, DC2 |
| Renewable generation | - | ✅ Complete | DC2 |
| Emissions & pricing | - | ✅ Complete | DC3, DC4 |
| **CHP** | `vedalang-c96` | 🔲 Not started | Multi-output processes |
| **Storage** | `vedalang-1ak` | 🔲 Not started | Same-commodity I/O |
| **Demand trajectories** | `vedalang-kpd` | 🔲 Not started | New scenario type? |
| **Fuel supply** | `vedalang-2cr` | 🔲 Not started | Resource limits |
| **Capacity bounds** | `vedalang-381` | 🔲 Not started | NCAP_BND, CAP_BND |
| **Timeslices** | `vedalang-6q7` | 🔲 Not started | Temporal structure |
| **Transmission** | `vedalang-1uu` | 🔲 Not started | HV/LV within region |
| **Trade** | `vedalang-87e` | 🔲 Not started | IRE processes |
| **User constraints** | `vedalang-9df` | 🔲 Not started | UC tables |

### Exploration Protocol

1. Pick one primitive at a time
2. Design minimal toy model in VedaLang
3. Validate with `veda_check --from-vedalang --json`
4. Iterate 2-3 times before proposing schema changes
5. Document in handoff: `experiments/handoff/session_YYYY-MM-DD.yaml`

---

## Toolchain Status

| Tool | Command | Purpose | Status |
|------|---------|---------|--------|
| **vedalang** | `uv run vedalang compile src.veda.yaml` | VedaLang → TableIR → Excel | ✅ Working |
| **veda_emit_excel** | `uv run veda_emit_excel tableir.yaml --out dir/` | TableIR → Excel | ✅ Working |
| **veda_check** | `uv run veda_check src.veda.yaml --from-vedalang` | Full pipeline validation | ✅ Working |
| **veda_pattern** | `uv run veda_pattern expand <pattern>` | Pattern expansion | ✅ Working |
| **xl2times** | `uv run xl2times dir/ --diagnostics-json` | VEDA validation oracle | ✅ Hardened |

---

## VedaLang Capabilities

### What VedaLang Can Express

| Concept | Schema Support | Validated In |
|---------|----------------|--------------|
| Single region models | ✅ | DC1, DC2, DC3, DC4 |
| Multi-region models | ✅ | DC5 |
| Energy commodities | ✅ | All DCs |
| Emission commodities | ✅ | DC3 |
| Thermal power plants | ✅ | DC1, DC2 |
| Renewable plants (no fuel input) | ✅ | DC2 |
| Process efficiency | ✅ | DC1, DC2, DC3 |
| Emission factors (output share) | ✅ | DC3 |
| CO2 price scenarios | ✅ | DC4 |
| Time-series parameters | ✅ | DC4 |

### What VedaLang Cannot Yet Express

| Concept | Status | Exploration Issue |
|---------|--------|-------------------|
| CHP (multi-output) | 🔲 To explore | `vedalang-c96` |
| Storage | 🔲 To explore | `vedalang-1ak` |
| Demand projections | 🔲 To explore | `vedalang-kpd` |
| Trade between regions | ❌ Needs IRE | `vedalang-87e` |
| Vintage/age tracking | ❌ Future | - |
| Timeslice definitions | ❌ Needs tables | `vedalang-6q7` |
| Capacity bounds | ❌ Needs attributes | `vedalang-381` |
| User constraints | ❌ Needs UC tables | `vedalang-9df` |

---

## Design Challenges Completed

| Challenge | Description | Schema Changes | Fixture |
|-----------|-------------|----------------|---------|
| **DC1** | Thermal plant via patterns | None | dc1_thermal_from_patterns.veda.yaml |
| **DC2** | Thermal + renewable sharing commodity | None | dc2_thermal_renewable.veda.yaml |
| **DC3** | Emission commodity + emission factor | None | dc3_with_emissions.veda.yaml |
| **DC4** | CO2 price trajectory scenario | Added `scenarios` | dc4_co2_price_scenario.veda.yaml |
| **DC5** | Two-region model | None | dc5_two_regions.veda.yaml |

---

## Infrastructure Components

### Schemas
- `vedalang/schema/vedalang.schema.json` - VedaLang source schema
- `vedalang/schema/tableir.schema.json` - Intermediate representation schema
- `vedalang/schema/diagnostics.schema.json` - xl2times diagnostic output
- `vedalang/schema/manifest.schema.json` - xl2times manifest output

### Pattern Library
- `rules/patterns.yaml` - 5 patterns (power plants, commodities, scenarios)
- `rules/constraints.yaml` - VEDA tag constraints and required fields
- `rules/decision_tree.yaml` - Intent routing for natural language

### Exploration Infrastructure
- `docs/exploration_prompt.md` - Full exploration protocol for agents
- `experiments/` - Directory structure for primitive exploration
- `experiments/handoff/` - Session continuity records

### Guardrails
- **Golden fixtures**: `tests/test_golden_fixtures.py` - auto-tests all examples
- **Schema compatibility**: `tests/test_schema_compatibility.py` - 16 tests preventing breaking changes
- **TableIR invariants**: `tools/veda_check/invariants.py` - fast validation before xl2times
- **Failure tracking**: `tests/failures/` - infrastructure for learning from failures

### Documentation
- `AGENTS.md` - Agent workflow, design phases, guardrails
- `docs/exploration_prompt.md` - Primitives exploration protocol
- `docs/baseline_diagnostics.md` - xl2times diagnostic codes
- `docs/schema_evolution.md` - Schema change policy
- `docs/pattern_validation.md` - Pattern validation catalog
- `docs/STATUS.md` - This file

---

## Test Coverage

```
134 tests passing

Key test files:
- test_vedalang_compiler.py - VedaLang → TableIR compilation
- test_vedalang_schema.py - Schema validation
- test_veda_emit_excel.py - Excel emission
- test_veda_check.py - Full pipeline
- test_golden_fixtures.py - All example fixtures
- test_schema_compatibility.py - Schema evolution guards
- test_tableir_invariants.py - Fast validation
- test_diagnostic_integration.py - xl2times diagnostics
- test_patterns_expand.py - Pattern expansion
```

---

## xl2times Modifications

We hardened xl2times (in `xl2times/` submodule) to emit structured diagnostics:

| Change | Purpose |
|--------|---------|
| `diagnostics.py` | New diagnostic collector infrastructure |
| `utils.py` | Added `require_table()`, `require_column()`, `require_scalar()` helpers |
| `transforms.py` | Defensive checks with diagnostic emission throughout |
| `__main__.py` | Top-level exception → diagnostics bridge |

**Diagnostic codes added:**
- `MISSING_REQUIRED_TABLE` - Table not present
- `MISSING_REQUIRED_COLUMN` - Column missing from table
- `INVALID_SCALAR_TABLE` - Wrong shape for scalar
- `MISSING_TIMESLICES` - No timeslice definitions
- `INTERNAL_ERROR` - Uncaught exception (with traceback)

---

## Repository Structure

```
veda-devtools/
├── AGENTS.md                 # Agent instructions
├── docs/
│   ├── STATUS.md             # This file
│   ├── exploration_prompt.md # Primitives exploration protocol
│   ├── baseline_diagnostics.md
│   ├── pattern_validation.md
│   └── schema_evolution.md
├── experiments/              # Primitives exploration
│   ├── handoff/              # Session continuity records
│   ├── chp/                  # CHP experiments
│   ├── storage/              # Storage experiments
│   ├── demand/               # Demand experiments
│   └── ...                   # Other primitives
├── vedalang/
│   ├── schema/               # JSON Schema definitions
│   ├── compiler/             # VedaLang → TableIR compiler
│   └── examples/             # Golden fixtures (DC1-DC5)
├── tools/
│   ├── veda_check/           # Unified validation CLI
│   ├── veda_emit_excel/      # TableIR → Excel emitter
│   └── veda_patterns/        # Pattern expansion tool
├── rules/
│   ├── patterns.yaml         # Pattern templates
│   ├── constraints.yaml      # VEDA tag constraints
│   └── decision_tree.yaml    # Intent routing
├── tests/
│   ├── failures/             # Failure tracking
│   └── *.py                  # 134 tests
├── fixtures/
│   └── MiniVEDA2/            # Reference VEDA model
└── xl2times/                 # Submodule (hardened)
```

---

## Commands Reference

```bash
# Validate a VedaLang model
uv run veda_check model.veda.yaml --from-vedalang --json

# Compile to TableIR only
uv run vedalang compile model.veda.yaml --tableir output.yaml

# Emit Excel from TableIR
uv run veda_emit_excel tableir.yaml --out output_dir/

# Expand a pattern
uv run veda_pattern expand add_power_plant \
  --param plant_name=MY_PLANT \
  --param fuel_commodity=COAL \
  --param output_commodity=ELC

# Run all tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .
```

---

## Issue Tracking

Using `bd` (beads) for issue tracking.

```bash
bd list --status open    # Show open issues (9 primitives + 1 epic)
bd list --status closed  # Show closed issues (29 implementation issues)
bd create "title"        # Create new issue
```

### Open Issues

| Issue | Title |
|-------|-------|
| `vedalang-fq8` | Epic: VedaLang Primitives Exploration |
| `vedalang-c96` | Explore CHP (Combined Heat and Power) |
| `vedalang-1ak` | Explore Storage |
| `vedalang-kpd` | Explore Demand & Demand Trajectories |
| `vedalang-2cr` | Explore Fuel Supply & Resource Limits |
| `vedalang-381` | Explore Capacity Bounds & Build Limits |
| `vedalang-6q7` | Explore Time-Slicing / Temporal Structure |
| `vedalang-1uu` | Explore Transmission Within a Region |
| `vedalang-87e` | Explore Trade Between Regions |
| `vedalang-9df` | Explore User Constraints / Policy Constraints |
