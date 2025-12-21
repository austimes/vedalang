Use 'bd' for task tracking

## Package Manager

This project uses **uv** as the Python package manager.

```bash
# Sync dependencies (install/update from lockfile)
uv sync

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run a command in the venv
uv run <command>

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run xl2times
uv run xl2times <args>
```

# VEDA DevTools - Agent Instructions

## Project Vision

Build a **safer, typed DSL** that compiles to VEDA tables — analogous to how TypeScript compiles to JavaScript. The new language (working name: **VedaLang**) provides:

- Type safety (units, symbols, constraints)
- Schema validation  
- Cross-reference checking
- Clear error messages

VEDA Excel tables become a **compiled artifact**, not the source. xl2times validates the compiled output.

## Architecture Overview

```
VedaLang Source (.veda.yaml)
    │
    │  (1) Parse + schema-validate
    ▼
VedaLang AST  ──►  TableIR (in-memory)
    │                  │
    │  (2) Type check  │  (3) Deterministic Excel emission
    ▼                  ▼
Typed VedaLang    VEDA Excel (.xlsx)
                      │
                      │  (4) xl2times --diagnostics-json
                      ▼
               TIMES DD files + Diagnostics
```

**Key insight**: VedaLang is the source; Excel is compiled output; xl2times is the validation oracle.

## Toolchain Build Order

Tools needed for an agent to **design VedaLang itself**:

| Order | Tool | Purpose |
|-------|------|---------|
| **T1** | `xl2times` + JSON outputs | Validation oracle — "Is this valid VEDA?" |
| **T2** | `veda_emit_excel` | TableIR → Excel emitter (test VEDA patterns) |
| **T3** | `vedalang` compiler | VedaLang → TableIR → Excel |
| **T4** | `veda_check` | Orchestration wrapper with unified diagnostics |

## Key Principle: Agent-Designed Language

The goal is for an **AI agent to iteratively design VedaLang** using feedback tools:

1. **xl2times validation** — "Did I produce valid VEDA tables?"
2. **veda_check** — Unified lint + compile + validate feedback
3. **Decision heuristics** — Mapping physical concepts → VEDA table patterns

We are NOT porting legacy models. This is for new model development.

## Two Separate Concerns

### 1. Language Mechanics (VedaLang)
- Syntax, types, allowed constructs
- Schema-defined (JSON Schema)
- Compiler lowers to TableIR → Excel

### 2. Modeling Decisions (Heuristics)
- "Given intent X, which tags/files/fields do I use?"
- Data-driven pattern library (`rules/patterns.yaml`)
- Agent discovers these through experimentation

**These are kept separate.** VedaLang is a general-purpose VEDA authoring language; heuristics are the "standard library" of patterns.

## Repository Structure

```
veda-devtools/
├── AGENTS.md                    # This file
├── docs/
│   └── VEDA2_NL_to_VEDA_PRD_v0_3.txt
├── vedalang/
│   ├── schema/                  # JSON Schema definitions
│   │   ├── vedalang.schema.json # VedaLang source schema
│   │   └── tableir.schema.json  # TableIR schema
│   ├── compiler/                # VedaLang → TableIR
│   └── examples/                # Example VedaLang sources
├── tools/
│   ├── veda_check/              # Unified validation CLI
│   └── veda_emit_excel/         # TableIR → Excel emitter
├── rules/
│   ├── patterns.yaml            # Concept → VedaLang templates
│   ├── decision_tree.yaml       # Intent routing
│   └── constraints.yaml         # Valid tag/file combinations
├── fixtures/
│   └── MiniVEDA2/               # Minimal test model
└── tests/
```

## Commands

```bash
# Emit Excel from TableIR (low-level, for pattern experimentation)
veda_emit_excel tables.yaml --out model.xlsx

# Compile VedaLang to Excel
vedalang compile src/ --out model.xlsx

# Validate Excel through xl2times
xl2times model.xlsx --case base --diagnostics-json diag.json

# Full pipeline: compile + validate (preferred)
veda_check src/ --from-vedalang --case base
```

## TableIR Example

The intermediate representation between VedaLang and Excel:

```yaml
files:
  - path: base/base.xlsx
    sheets:
      - name: "Base"
        tables:
          - tag: "~FI_PROCESS"
            rows:
              - { PRC: "PP_CCGT", Sets: "ELE", TACT: "PJ", TCAP: "GW" }
          - tag: "~FI_T"
            rows:
              - { PRC: "PP_CCGT", COM_IN: "NG", COM_OUT: "ELC", EFF: 0.55 }
```

## xl2times Integration

xl2times is the **validation oracle** for compiled output. Required extensions:

- `--diagnostics-json <path>` — Structured error output
- `--manifest-json <path>` — What was parsed and how

These outputs tell the agent whether the VEDA tables it generated are valid.

## Schema-Based Design

VedaLang and TableIR are defined via **JSON Schema**:

- Enables agent introspection of valid constructs
- Tooling (validators, docs) derived from schemas
- Tests ensure schema ↔ implementation alignment

Cross-reference checks and semantic constraints live in code/rules, not just schema.

## Decision Heuristics (Pattern Library)

Mapping physical/modeling concepts to VEDA patterns:

```yaml
# rules/patterns.yaml
patterns:
  add_power_plant:
    description: "Thermal generation process"
    veda_templates:
      - type: process
        technology_type: "thermal"
        default_efficiency: 0.55
        # expands into ~FI_PROCESS + ~FI_T
  
  co2_price_trajectory:
    veda_templates:
      - type: scenario_parameter
        tag: "~TFM_INS-TS"
        commodity: "CO2"
```

The agent discovers and refines these heuristics through experimentation.

## Guardrails

- **xl2times is single source of truth** — any discrepancy is a bug
- **Test-driven expansion** — no new tag/pattern without passing test
- **Schema-first changes** — update schema → docs → tests → code
- **Heuristic discipline** — every pattern must link to a fixture example

## Notes for AI Agents

- Excel is OUTPUT, not source — never edit Excel directly
- Always validate through `veda_check` after generating tables
- VedaLang schema is evolving — propose improvements via schema changes
- Decision heuristics are learned, not hardcoded
- TableIR is your experimentation layer before committing to VedaLang syntax

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
