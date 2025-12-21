# Failure Records

This directory captures failures encountered during VedaLang design exploration.
Every failure becomes a learning opportunity and potential test case.

## Purpose

When an agent explores VedaLang and hits failures, we:
1. Capture the failure systematically
2. Learn from it (what went wrong, why)
3. Convert it to a regression test

## Failure Types

| Type | Description | Action |
|------|-------------|--------|
| **A** | Wrong VEDA structure | Fix TableIR, re-validate |
| **B** | VedaLang can't express valid pattern | Extend VedaLang schema |
| **C** | Compiler bug | Fix compiler, add regression test |

## Failure Record Schema

Each failure is recorded as a YAML file with the following structure:

```yaml
# Unique identifier (also the filename without extension)
id: missing_sets_column

# When the failure was encountered
date: 2024-12-21

# Failure type: A, B, or C (see above)
type: A

# What the agent was trying to accomplish
intent: "Create a process without specifying sets"

# The input that caused the failure
input:
  format: vedalang  # or tableir
  content: |
    model:
      name: Test
      processes:
        - name: PROC1
          # missing sets field

# Which tool produced the error
tool: veda_check  # or xl2times, vedalang, veda_emit_excel

# The error that was produced
error:
  code: MISSING_REQUIRED_FIELD
  message: "Process 'PROC1' missing required field 'sets'"

# How the issue was resolved (after investigation)
resolution: |
  Sets field is required. Added sets: [ELE] to process definition.

# Reference to the test that was added (once the loop is closed)
test_added: tests/test_vedalang_schema.py::test_missing_sets_rejected
```

## Failure-to-Test Workflow

1. **Reproduce** - Reproduce failure with minimal input
2. **Record** - Save to `tests/failures/{id}.yaml` using the schema above
3. **Investigate** - Determine the root cause and failure type
4. **Fix** - Apply the appropriate fix based on failure type
5. **Test** - Write a test that:
   - For Type A: expects xl2times error diagnostic
   - For Type B: documents the gap (skip with reason until fixed)
   - For Type C: expects correct behavior after fix
6. **Close** - Update the failure record with `resolution` and `test_added`

## Recording Failures Programmatically

Use the `record_failure()` helper in `tests/conftest.py`:

```python
from tests.conftest import record_failure

record_failure(
    id="missing_sets_column",
    intent="Create a process without specifying sets",
    input_content="model:\n  name: Test\n  processes:\n    - name: PROC1",
    input_format="vedalang",
    tool="veda_check",
    error_code="MISSING_REQUIRED_FIELD",
    error_message="Process 'PROC1' missing required field 'sets'",
    failure_type="A",
)
```

## File Naming

- Use lowercase with underscores: `missing_sets_column.yaml`
- Make the ID descriptive of the failure
- Keep IDs unique across all failure records
