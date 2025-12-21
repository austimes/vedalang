# Demand & Demand Trajectories Exploration

## Summary

**Status:** PARTIALLY EXPRESSIBLE - Schema extension needed

### What WORKS with current schema:
1. ✅ **Demand commodities** - `type: demand` maps correctly to `csets: DEM`
2. ✅ **Demand processes** - Processes can output to demand commodities
3. ✅ **Topology** - `~FI_T` with commodity-in/commodity-out works

### What DOES NOT WORK:
1. ❌ **Demand projections (COM_PROJ)** - No scenario type to express demand levels over time
   - Current `commodity_price` type maps to `COM_PRICE`, not `COM_PROJ`
   - Need a new scenario type `demand_projection`

## VEDA Pattern for Demand Projections

In VEDA, demand projections are specified via `~FI_T` with:
- `attribute: DEMAND` (maps to TIMES `COM_PROJ`)
- `commodity: <demand_commodity>`
- `year: <year>`
- `value: <demand_level>`

Example (validated with xl2times):
```yaml
# In ~FI_T table
- attribute: DEMAND
  commodity: RSD
  year: 2020
  value: 100.0
```

## Proposed Schema Extension

Add new scenario type `demand_projection`:

```json
{
  "type": "string",
  "enum": ["commodity_price", "demand_projection"],
  ...
}
```

### VedaLang Syntax

```yaml
scenarios:
  - name: BaseDemand
    type: demand_projection
    commodity: RSD
    interpolation: interp_extrap
    values:
      "2020": 100.0
      "2030": 120.0
      "2040": 140.0
      "2050": 160.0
```

### Compiler Emission

For `demand_projection` type, emit `~FI_T` rows:
```yaml
- tag: ~FI_T
  rows:
    - attribute: DEMAND
      commodity: RSD
      year: 2020
      value: 100.0
    # ... one row per year
```

## Files

- `model_demand_v1.veda.yaml` - Basic demand model (passes)
- `model_demand_v2_attempt.veda.yaml` - Attempts to use commodity_price for demand (wrong semantics)
- `demand_v1_tableir.yaml` - Generated TableIR from v1
- `demand_v2_tableir.yaml` - Generated TableIR from v2
- `demand_v3_tableir_manual.yaml` - Manually crafted TableIR with demand projections (validates pattern)

## Validation Results

### v1 (basic demand commodity)
```
✓ PASS - 0 errors, 1 warning (MISSING_TIMESLICES)
```

### v3 (manual TableIR with COM_PROJ)
```
✓ PASS - 0 errors, 1 warning (MISSING_TIMESLICES)
Demand projections correctly appear in ~FI_T with attribute=DEMAND
```
