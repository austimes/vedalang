# Timeslice Exploration

## Status: ✅ VALIDATED

Successfully validated timeslice definitions in VEDA. Zero warnings, zero errors.

## Purpose
Explore VEDA timeslice structure for VedaLang primitive design.

## Key Results

**Working TableIR:** `mini_plant_with_timeslices.tableir.yaml`

Validated with `veda_check --from-tableir`:
- 10 tables, 19 rows
- 0 warnings, 0 errors

## VEDA Timeslice Structure

### Key Findings

**1. `~TIMESLICES` Table (in SysSettings)**
- Defines hierarchical timeslice tree via columns: `SEASON`, `WEEKLY`, `DAYNITE`
- Each column contains short codes
- xl2times extracts unique values per column, then creates cross-product
- Example: `SEASON={S,W}` × `DAYNITE={D,N}` → `{SD, SN, WD, WN}`

```yaml
# TableIR format (lowercase columns)
- tag: "~TIMESLICES"
  rows:
    - season: S
      weekly: ""
      daynite: D
    - season: W
      weekly: ""
      daynite: N
```

**2. `YRFR` Attribute (Year Fraction)**
- Specified via `~TFM_INS` table with `YRFR` attribute
- Each timeslice gets a fraction (must sum to 1.0)
- Maps to `G_YRFR` parameter in TIMES

```yaml
- tag: "~TFM_INS"
  rows:
    - timeslice: SD
      attribute: YRFR
      allregions: 0.25
    - timeslice: SN
      attribute: YRFR
      allregions: 0.23
    - timeslice: WD
      attribute: YRFR
      allregions: 0.25
    - timeslice: WN
      attribute: YRFR
      allregions: 0.27
```

**3. Timeslice Hierarchy Levels (TSLVL)**
- `ANNUAL`: Top level (fraction = 1.0)
- `SEASON`: Seasonal variation (e.g., Summer, Winter)
- `WEEKLY`: Weekly variation (rarely used)
- `DAYNITE`: Day/night or time-of-day variation

**4. Critical: Region Recognition**

For xl2times to recognize regions as "internal" (and process timeslices):
- BookRegions_Map bookname must match file pattern `VT_{BookName}_*`
- Example: `bookname: REG1` requires file `VT_REG1_*.xlsx`

```yaml
- tag: "~BOOKREGIONS_MAP"
  rows:
    - bookname: REG1  # Must match VT_REG1_*.xlsx
      region: REG1
```

### How xl2times Processes This

From `transforms.py::process_time_slices()`:
1. Reads SEASON, WEEKLY, DAYNITE columns from `~TIMESLICES`
2. Extracts unique values per column
3. Creates cross-product for each internal region
4. Concatenates names: SEASON + WEEKLY + DAYNITE → timeslice name
5. Builds `ts_tslvl` (timeslice → level mapping)
6. Builds `ts_map` (parent → child mapping)

**Important:** Only runs if `model.internal_regions` is non-empty!

## Files in This Directory

- `mini_plant_with_timeslices.tableir.yaml` - ✅ VALIDATED complete example
- `timeslices_v2.tableir.yaml` - Timeslices only (no model)
- `timeslices_annual.tableir.yaml` - ANNUAL-only (simplest)
- `timeslices_seasonal.tableir.yaml` - 4 timeslices draft

## VedaLang Schema Proposal

See `schema_proposal.yaml` for proposed VedaLang additions.

### Proposed `timeslices` Section

```yaml
model:
  timeslices:
    # Define levels and their codes
    season:
      - code: S
        name: Summer
        days: 175  # Optional, for documentation
      - code: W
        name: Winter
        days: 190
    daynite:
      - code: D
        name: Day
      - code: N
        name: Night
    
    # Year fractions (required for non-ANNUAL timeslices)
    fractions:
      SD: 0.25
      SN: 0.23
      WD: 0.25
      WN: 0.27
```

This would compile to:
1. `~TIMESLICES` table with Season/DayNite columns
2. `~TFM_INS` rows with YRFR attribute

## Constraints Discovered

1. **Year fractions must sum to 1.0** (or very close)
2. **Region file naming matters** - VT_{BookName}_* pattern required
3. **Timeslice names are auto-generated** - SEASON + WEEKLY + DAYNITE concatenation
4. **ANNUAL is implicit** - Always present at top level
