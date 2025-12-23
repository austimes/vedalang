# VedaLang

A typed DSL that compiles to VEDA tables for TIMES energy system models.

VedaLang provides type safety, schema validation, and clear error messages while compiling to VEDA Excel tables that can be processed by xl2times and solved with GAMS/TIMES.

```
VedaLang Source (.veda.yaml) → Compiler → VEDA Excel (.xlsx) → xl2times → TIMES DD files
```

---

## Two Ways to Use This Repository

| Goal | You are a... | Start here |
|------|--------------|------------|
| **Author energy system models** using VedaLang | Model Developer | [Using VedaLang](#using-vedalang) |
| **Extend or improve** the VedaLang language itself | Language Designer | [Developing VedaLang](#developing-vedalang) |

---

## Using VedaLang

Write `.veda.yaml` files to define energy system models. The compiler handles Excel generation and validation.

### Documentation

- **[docs/vedalang-user/LLMS.md](docs/vedalang-user/LLMS.md)** — Comprehensive guide for authoring VedaLang models
- **[vedalang/examples/](vedalang/examples/)** — Example models
- **[vedalang/schema/vedalang.schema.json](vedalang/schema/vedalang.schema.json)** — Language schema
- **[rules/patterns.yaml](rules/patterns.yaml)** — Pattern "standard library"

### Quick Start

```bash
# Install
git clone https://github.com/austimes/vedalang.git
cd vedalang
uv sync

# Validate a model
uv run veda-dev check model.veda.yaml --from-vedalang

# Run full pipeline (VedaLang → Excel → DD → TIMES)
uv run veda-dev pipeline model.veda.yaml --no-solver
```

### Minimal Example

```yaml
model:
  name: MinimalExample
  regions: [REG1]
  
  commodities:
    - name: ELC
      type: energy
      unit: PJ

  processes:
    - name: PP_GEN
      sets: [ELE]
      primary_commodity_group: NRGO
      outputs:
        - commodity: ELC
```

---

## Developing VedaLang

Extend the VedaLang DSL, improve the compiler, or discover new VEDA patterns.

### Documentation

- **[AGENTS.md](AGENTS.md)** — Primary instructions for the VedaLang Design Agent
- **[docs/vedalang-design-agent/](docs/vedalang-design-agent/)** — Design workflows, schema evolution, pattern validation

### Key Concepts

- **xl2times is the oracle** — Its verdict on compiled Excel is final
- **Schema-first design** — Update JSON Schema before compiler changes
- **TableIR experimentation** — Prototype at TableIR level, lift to VedaLang when valid

### Design Workflow

```
1. Prototype at TableIR level (raw YAML tables)
2. Emit Excel: veda_emit_excel tables.yaml --out test.xlsx
3. Validate: xl2times test.xlsx --diagnostics-json diag.json
4. If valid → lift pattern to VedaLang syntax
5. If invalid → fix and retry
```

### Development Commands

```bash
# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Validate the mini_plant example
uv run veda_check vedalang/examples/mini_plant.veda.yaml --from-vedalang
```

---

## Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- GAMS with a valid license (for running the solver)
- TIMES source code

### Setup

```bash
# Clone and install
git clone https://github.com/austimes/vedalang.git
cd vedalang
uv sync
uv pip install -e .

# Configure environment
cp .env.example .env
# Edit .env to set TIMES_SRC=/path/to/your/TIMES_model
```

### Getting TIMES Source

```bash
git clone https://github.com/etsap-TIMES/TIMES_model.git ~/TIMES_model
```

Then set `TIMES_SRC` in your `.env` file to point to this directory.

---

## Project Structure

```
veda-devtools/
├── vedalang/              # VedaLang compiler and schema
│   ├── compiler/          # VedaLang → TableIR compiler
│   ├── schema/            # JSON Schema definitions
│   └── examples/          # Example VedaLang models
├── tools/
│   ├── veda_dev/          # Unified CLI (veda-dev)
│   ├── veda_check/        # Validation tool
│   ├── veda_emit_excel/   # TableIR → Excel emitter
│   └── veda_run_times/    # GAMS/TIMES runner
├── xl2times/              # Local fork of xl2times (Excel → DD)
├── rules/                 # Pattern library
├── docs/
│   ├── vedalang-user/     # Documentation for model authors
│   └── vedalang-design-agent/  # Documentation for language designers
└── tests/                 # Test suite
```

---

## License

See LICENSE file for details.
