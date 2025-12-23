# VEDA Table Schema Design (vedalang-em5)

Investigation into Python dataclass schemas for VEDA table validation.

## Recommendation: Dataclasses (not Pydantic)

Use small, explicit Python `@dataclass` schemas auto-populated from `veda-tags.json` with manual overlays for layout rules.

**Why dataclasses over Pydantic:**
- Standard library, no new dependency
- Already using runtime validation via `jsonschema`
- Easy to build programmatically from veda-tags.json
- Pydantic's type coercion not wanted for VEDA tables

## Core Schema Dataclasses

```python
from dataclasses import dataclass, field
from typing import Optional, Set, Dict, List, Literal

LayoutKind = Literal["long", "wide"]

@dataclass
class VedaFieldSchema:
    name: str                              # Canonical internal name (use_name)
    header_names: Set[str]                 # All allowed header names (name + aliases)
    required: bool = False                 # Required per row
    multi_valued: bool = False             # Comma-separated list
    valid_values: Optional[Set[str]] = None  # Enum-like restriction
    query_field: bool = False              # pset_ci, cset_cd, etc.

@dataclass
class VedaTableLayout:
    kind: LayoutKind                       # "long" or "wide"
    index_fields: List[str]                # Row index columns
    attribute_field: Optional[str] = None  # For long format
    value_field: Optional[str] = None      # For long format
    allow_value_column: bool = True        # FI-style tables set False

@dataclass  
class VedaTableSchema:
    tag_name: str
    variant: Optional[str] = None          # e.g., "AT" for ~TFM_DINS-AT
    layout: VedaTableLayout
    fields: Dict[str, VedaFieldSchema]
    allowed_headers: Set[str]
    forbidden_headers: Set[str] = field(default_factory=set)
    mutually_exclusive_groups: List[Set[str]] = field(default_factory=list)
    require_any_of: List[Set[str]] = field(default_factory=list)
```

## Field Validation from veda-tags.json

### Required vs Optional
- `remove_any_row_if_absent: true` → required
- `remove_first_row_if_absent: true` → required
- `add_if_absent: true` + `default_to` → optional with default
- Otherwise → optional

### Enum-like Fields
From `valid_values` in veda-tags.json:
```json
{
  "name": "top_check",
  "valid_values": ["A", "I", "O"]
}
```

### Multi-valued Fields
From `comma-separated-list: true` in veda-tags.json.

## Layout Rules (Manual Overlays)

veda-tags.json doesn't encode layouts, so apply manually:

### ~FI_T (long format, attributes as columns)
```python
fi_t_schema.layout = VedaTableLayout(
    kind="long",
    index_fields=["region", "commodity", "year"],
    attribute_field="attribute",
    value_field="value",
    allow_value_column=True,
)
```

### ~TFM_DINS-AT (wide format, attributes as columns)
```python
tfm_dins_at_schema.layout = VedaTableLayout(
    kind="wide",
    index_fields=["region", "process", "year"],
    allow_value_column=False,
)
tfm_dins_at_schema.forbidden_headers |= {"value", "attribute"}
```

### ~UC_T (long format with query fields)
```python
uc_t_schema.layout = VedaTableLayout(
    kind="long",
    index_fields=["region", "uc_n", "year"],
    value_field="value",
    allow_value_column=True,
)
uc_t_schema.mutually_exclusive_groups.append({"cset_cd", "cset_cn", "cset_set"})
```

## Integration Points

Validate TableIR before Excel emission:

```python
model = load_and_validate_model_json(...)
tableir = compile_vedalang_to_tableir(model)
validate_tableir_against_veda_schemas(tableir)  # NEW
emit_excel_from_tableir(tableir, output_dir)
```

## Error Messages

Good error message patterns:
- Unknown column: `~FI_T: unknown column 'comodity'. Did you mean 'commodity'?`
- Missing required: `~FI_T: missing required column 'commodity'.`
- Per-row: `~FI_T row 12 (region=R1, commodity=ELC, year=2030): attribute 'DEMANDX' is not valid`

## Implementation Plan

1. **Auto-generate field schemas** from veda-tags.json (~1h)
2. **Add manual layout overlays** for ~FI_T, ~TFM_DINS-AT, ~UC_T (~1h)
3. **Implement validation function** in compiler.py (~2h)
4. **Add tests** for schema validation errors (~1h)

Total estimated effort: ~5h (S-M)
