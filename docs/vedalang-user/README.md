# VedaLang User Documentation

This documentation is for AI agents and humans who **use VedaLang** to author energy system models.

## What is VedaLang?

VedaLang is a typed DSL that compiles to VEDA Excel tables. You write `.veda.yaml` files, and the compiler generates the Excel files that xl2times processes into TIMES models.

```
VedaLang Source (.veda.yaml)  →  VEDA Excel (.xlsx)  →  TIMES DD files
```

## Quick Start

1. Read [LLMS.md](LLMS.md) — the comprehensive LLM guide for authoring VedaLang
2. Study the examples in `vedalang/examples/`
3. Check the schema at `vedalang/schema/vedalang.schema.json`
4. Use patterns from `rules/patterns.yaml`

## Key Resources

| Resource | Description |
|----------|-------------|
| [LLMS.md](LLMS.md) | LLM guide for authoring VedaLang models |
| `vedalang/schema/vedalang.schema.json` | Formal language schema |
| `vedalang/examples/` | Example `.veda.yaml` models |
| `rules/patterns.yaml` | Pattern "standard library" |

## Validation

Always validate your models:

```bash
# Compile and validate a VedaLang model
uv run veda_check your_model.veda.yaml --from-vedalang
```

## What This Documentation Does NOT Cover

- How to extend or modify VedaLang itself
- Compiler internals and schema evolution
- Design workflows and experimentation

For those topics, see `docs/vedalang-design-agent/`.
