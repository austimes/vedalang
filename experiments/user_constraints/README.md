# User Constraints Exploration

## Overview

User constraints (UC) in TIMES/VEDA allow arbitrary linear relationships between model variables. They are the most complex primitive because they can express:

- **Policy targets**: e.g., "Renewables ≥ 30% of electricity generation"
- **Technology relationships**: e.g., "CHP heat output matches heating demand"
- **Emission caps**: e.g., "Total CO2 ≤ 100 Mt in 2030"
- **Custom equations**: Linear combinations of activities, capacities, flows

## VEDA UC Table Structure

### Key Tables

| Table | Purpose |
|-------|---------|
| `~UC_T` | Main UC data table (coefficients, RHS values) |
| `~UC_SETS` | Declare UC scope (regions, periods, timeslices) |

### UC Sets (Scope Declaration)

Before a `~UC_T` table, you declare how constraints apply:

- `R_E` (region each) - Constraint applies to each region separately
- `R_S` (region sum) - Constraint sums across regions
- `T_E` (time each) - Constraint applies to each period separately
- `T_S` (time sum) - Constraint cumulative across periods
- `TS_E` (timeslice each) - Constraint per timeslice

Example:
```
~UC_Sets: R_E: AllRegions
~UC_Sets: T_E:
```

### UC_T Columns (from veda-tags.json)

**Key columns:**
- `uc_n` - Constraint name (identifier)
- `region` - Region(s) affected
- `attribute` - UC coefficient type (UC_ACT, UC_CAP, UC_FLO, UC_COMPRD, UC_COMNET, etc.)
- `side` - LHS or RHS (default: LHS)
- `limtype` - UP, LO, FX (for RHS)
- `value` / year columns - Coefficient or RHS values
- `pset_pn` / `process` - Process filter
- `cset_cn` / `commodity` - Commodity filter

### UC Attribute Types (UC_GRPTYPE)

From times-sets.json:
- `ACT` - Process activity (UC_ACT)
- `CAP` - Total capacity (UC_CAP)
- `NCAP` - New capacity (UC_NCAP)
- `FLO` - Flow variable (UC_FLO)
- `COMNET` - Net commodity production (UC_COMNET)
- `COMPRD` - Total commodity production (UC_COMPRD)
- `COMCON` - Commodity consumption (UC_COMCON)
- `IRE` - Inter-regional exchange (UC_IRE)

### RHS Attributes

Right-hand side values use different attributes based on scope:
- `UC_RHS` - Static RHS (no year/region)
- `UC_RHSR` - Region-specific RHS
- `UC_RHSRT` - Region+Year specific RHS
- `UC_RHSRTS` - Region+Year+Timeslice specific RHS
- `UC_RHSTS` - Year+Timeslice specific RHS

## Common UC Patterns

### 1. Activity Share Constraint (RPS-style)

"Wind + Solar ≥ 30% of total electricity generation"

```
~UC_Sets: R_E: REG1
~UC_Sets: T_E:
~UC_T: UC_RHSRT
| uc_n        | attribute | pset_pn   | cset_cn | side | year | value |
|-------------|-----------|-----------|---------|------|------|-------|
| REN_SHARE   | UC_COMPRD | PP_WIND   | ELC     | LHS  |      | 1     |
| REN_SHARE   | UC_COMPRD | PP_SOLAR  | ELC     | LHS  |      | 1     |
| REN_SHARE   | UC_COMPRD | *         | ELC     | RHS  |      | 0.3   |
```

The equation: `COMPRD(PP_WIND, ELC) + COMPRD(PP_SOLAR, ELC) >= 0.3 * COMPRD(*, ELC)`

### 2. Emission Cap

"Total CO2 ≤ 100 Mt in each year"

```
~UC_Sets: R_E: AllRegions
~UC_Sets: T_E:
~UC_T: UC_RHSRT
| uc_n     | attribute  | cset_cn | side | limtype | year | value |
|----------|------------|---------|------|---------|------|-------|
| CO2_CAP  | UC_COMNET  | CO2     | LHS  |         |      | 1     |
| CO2_CAP  | UC_RHSRT   |         | RHS  | UP      | 2030 | 100   |
```

### 3. Capacity Share

"Nuclear ≤ 40% of total generation capacity"

Uses `UC_CAP` attribute on LHS, capacity weighted RHS.

### 4. Growth Rate Constraint

"Annual capacity growth ≤ 20%"

Uses `UC_ATTR` with `GROWTH` modifier and `UC_CAP`.

## Experiment Files

| File | Pattern | Status |
|------|---------|--------|
| `tableir_uc_v1_minimal.yaml` | Minimal UC structure test | TBD |
| `tableir_uc_v2_emission_cap.yaml` | Emission cap constraint | TBD |
| `tableir_uc_v3_activity_share.yaml` | RPS-style share constraint | TBD |

## Key Learnings

1. **UC_SETS are required** - Must declare scope before ~UC_T table
2. **Side matters** - LHS terms are summed, RHS defines the bound
3. **Attribute type determines variable** - UC_ACT for activity, UC_COMPRD for production
4. **RHS attribute varies by scope** - UC_RHSRT for year-specific, UC_RHSRTS for timeslice-specific
5. **Wildcards work** - Can use `*` for process/commodity to mean "all"

## Complexity Assessment

User constraints are inherently complex. Recommended phased approach:

### Phase 1: Pre-built constraint types (VedaLang v1)
- `emission_cap` - Total emissions limit
- `activity_share` - Share of activity within sector
- `capacity_limit` - Absolute capacity limits (already in schema as bounds)

### Phase 2: General constraints (VedaLang v2)
- `constraint` - General linear constraint syntax
- Support for arbitrary LHS/RHS terms

## Open Questions

1. How does xl2times process UC_SETS declarations?
2. What's the minimal valid UC table structure?
3. Can we validate UC structure without running TIMES?
