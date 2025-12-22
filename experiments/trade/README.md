# Trade Between Regions Exploration

## Issue: vedalang-87e

## Goal
Determine if VedaLang can express inter-regional trade (IRE processes).

## Summary

**VERDICT: Trade requires VedaLang schema extension.**

Current VedaLang cannot express trade. A `trade_links` construct is needed.

## Findings

### How VEDA/TIMES Models Trade

From xl2times analysis and successful experiment:

1. **`~TRADELINKS` table** - Matrix format (origin regions vs destination regions)
   - Sheet name encodes direction: `Bi_COMMODITY` or `Uni_COMMODITY`
   - Commodity name as first column header
   - Region names as column/row headers
   - Values: 1 for trade link, or process name

2. **`~TRADELINKS_DINS`** - Normalized format with columns:
   - `reg1` (origin), `reg2` (destination)
   - `comm` (traded commodity)
   - `comm1`, `comm2` (can differ for conversion)
   - `process` (trade process name)
   - `tradelink` ('u' unidirectional, 'b' bidirectional)

3. **IRE process set** - Trade processes auto-belong to `IRE` set
4. **`TOP_IRE`** output: `(Origin, IN, Destination, OUT, Process)`
5. **Process naming**: `T{B|U}_{COMM}_{REG1}_{REG2}_##` auto-generated

### Validated VEDA Structure (miniveda2_with_trade)

Successfully created bidirectional ELC trade between REG1 and REG2:

```
TOP_IRE output:
REG1,ELC,REG2,ELC,TB_ELC_REG1_REG2_01  (export)
REG2,ELC,REG1,ELC,TB_ELC_REG1_REG2_01  (import)
```

Trade process belongs to IRE set in BOTH regions.

### Current VedaLang Capabilities

VedaLang can express:
- Multiple regions ✅
- Processes with IRE set ✅ (but no bi-regional topology)
- Basic topology (inputs/outputs) ✅

VedaLang CANNOT currently express:
- Bi-regional topology (origin/destination) ❌
- Trade direction (uni/bidirectional) ❌
- Auto-generated trade process names ❌
- `~TRADELINKS` or `~TRADELINKS_DINS` tables ❌

### Proposed Schema Extension

```yaml
model:
  trade_links:
    - origin: REG1
      destination: REG2
      commodity: ELC
      bidirectional: true
      efficiency: 0.98  # Optional: IRE_FLO (2% loss)
      capacity: 10.0    # Optional: NCAP_BND
```

This would compile to:
1. `~TRADELINKS_DINS` table with auto process naming
2. (Process auto-created by xl2times from TRADELINKS)
3. Optional efficiency/capacity via `~FI_T` attributes

## Experiments

1. `v1_workaround.veda.yaml` - Using existing constructs - **FAILS to capture trade semantics**
2. `v2_tableir_trade.yaml` - Direct TableIR - schema issues with complex SysSettings
3. `v3_tableir_trade.yaml` - Direct TableIR - schema issues
4. `miniveda2_with_trade/` - **SUCCESS** - Extended MiniVEDA2 with trade file

## Next Steps

1. Add `trade_links` to `vedalang.schema.json`
2. Implement compiler lowering to `~TRADELINKS_DINS`
3. Support optional efficiency (IRE_FLO) and capacity (NCAP_BND)
