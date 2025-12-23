# VedaLang

A typed DSL that compiles to VEDA tables for TIMES energy system models.

VedaLang provides type safety, schema validation, and clear error messages while compiling to VEDA Excel tables that can be processed by xl2times and solved with GAMS/TIMES.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- GAMS with a valid license (for running the solver)
- TIMES source code

### Installation

```bash
# Clone the repository
git clone https://github.com/austimes/vedalang.git
cd vedalang

# Install dependencies and the package in editable mode
uv sync
uv pip install -e .
```

### Environment Setup

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` to set your TIMES source path:

```bash
# Path to TIMES source code (required for running GAMS solver)
TIMES_SRC=/path/to/your/TIMES_model

# Optional: Path to GAMS executable if not in PATH
# GAMS_BINARY=/opt/gams/gams
```

#### Getting TIMES Source

TIMES is the energy system model that VedaLang targets. You need a copy of the TIMES source code:

```bash
# Clone the TIMES model (example - check IEA-ETSAP for current location)
git clone https://github.com/etsap-TIMES/TIMES_model.git ~/TIMES_model
```

Then set `TIMES_SRC` in your `.env` file to point to this directory.

## Usage

### Full Pipeline

Run the complete VedaLang → Excel → DD → TIMES pipeline:

```bash
# Run full pipeline (requires GAMS and TIMES_SRC)
uv run veda-dev pipeline model.veda.yaml

# Run without solver (stops after generating DD files)
uv run veda-dev pipeline model.veda.yaml --no-solver

# Verbose output with JSON results
uv run veda-dev pipeline model.veda.yaml --verbose --json
```

### Individual Tools

```bash
# Compile VedaLang to Excel
uv run vedalang compile src/model.veda.yaml --out output/

# Validate a model
uv run veda-dev check model.veda.yaml --from-vedalang

# Run xl2times on Excel files
uv run xl2times excel_dir/ --dd --output_dir dd/ --regions REG1,REG2

# Run TIMES solver on DD files
uv run veda-dev run-times dd_dir/ --times-src ~/TIMES_model
```

### Example Model

A comprehensive example model is included:

```bash
# Run the MiniSystem stress test model
uv run veda-dev pipeline vedalang/examples/minisystem.veda.yaml --verbose
```

## Project Structure

```
veda-devtools/
├── vedalang/           # VedaLang compiler and schema
│   ├── compiler/       # VedaLang → TableIR compiler
│   ├── schema/         # JSON Schema definitions
│   └── examples/       # Example VedaLang models
├── tools/
│   ├── veda_dev/       # Unified CLI (veda-dev)
│   ├── veda_check/     # Validation tool
│   ├── veda_emit_excel/# TableIR → Excel emitter
│   └── veda_run_times/ # GAMS/TIMES runner
├── xl2times/           # Local fork of xl2times (Excel → DD)
├── rules/              # Pattern library
└── tests/              # Test suite
```

## Development

```bash
# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker (if configured)
uv run ruff check . --select=E,W,F
```

## License

See LICENSE file for details.
