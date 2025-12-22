# Primary Commodity Group (PCG) Investigation

**Issue:** vedalang-hq1  
**Date:** 2024-12-22

## 1. What PCG Does in TIMES

The **Primary Commodity Group (PCG)** is fundamental to TIMES modeling:

### Purpose

1. **Defines Process Activity**: The sum of flows in the PCG equals the process activity (VAR_ACT)
2. **Defines Capacity**: Capacity is related to activity through the PCG flows
3. **Controls EQ_PTRANS**: The transformation equation uses PCG to define which side (input/output) is "primary" and which is "shadow"
4. **Peak Contribution**: For peaking constraints, if the peaking commodity is the only member of PCG, capacity contributes to peak; otherwise, actual production is used

### Key Quote from TIMES Documentation (Part I, Section 2.7):

> "TIMES requires the definition of Primary Commodity Groups (pcg), i.e. subsets of commodities *of the same nature* entering or leaving a process. TIMES utilizes the pcg to define the activity of the process, and also its capacity."

### Commodity Types That Can Form PCG

The valid commodity set types (csets) for PCG, in priority order:
- **DEM** (Demand)
- **MAT** (Material)  
- **NRG** (Energy)
- **ENV** (Environment/Emissions)
- **FIN** (Financial)

## 2. xl2times Inference Rules

### Location: `transforms.py`

The inference is done in two functions:

### 2.1 `_process_comm_groups_vectorised` (lines 1535-1583)

**Algorithm:**
```python
csets_ordered_for_pcg = ["DEM", "MAT", "NRG", "ENV", "FIN"]

for each (region, process) group:
    # Try OUTPUT first, then INPUT
    for io in ["OUT", "IN"]:
        # Try commodity types in priority order
        for cset in csets_ordered_for_pcg:  # DEM, MAT, NRG, ENV, FIN
            if process has commodity of type `cset` on side `io`:
                set DefaultVedaPCG = True for that commodity group
                break (stop searching)
```

**Plain English:**
1. First, look for OUTPUT commodities of type DEM, MAT, NRG, ENV, FIN (in that order)
2. If found, that's the default PCG
3. If no outputs found, look for INPUT commodities in the same order
4. The first match wins

### 2.2 `fill_in_missing_pcgs` (lines 1760-1806)

Handles two cases:
1. **Explicit suffix notation**: If `primarycg` is set to a suffix like "NRGO" (NRG + O for output), expand it to `PROCESSNAME_NRGO`
2. **Missing PCG**: Use the `DefaultVedaPCG` from topology to fill in

### 2.3 Default PCG Suffixes

Valid suffixes (from line 24-26):
```python
default_pcg_suffixes = [
    cset + io for cset in csets_ordered_for_pcg for io in ["I", "O"]
]
# Results in: ["DEMI", "DEMO", "MATI", "MATO", "NRGI", "NRGO", "ENVI", "ENVO", "FINI", "FINO"]
```

## 3. When Getting PCG Wrong Causes Problems

### 3.1 Efficiency Definition (EQ_PTRANS)

The PCG determines which side of the process defines activity:
- If PCG is on OUTPUT: `efficiency = output_flow / input_flow`
- If PCG is on INPUT: `efficiency = output_flow / input_flow` (but activity = input)

Getting this wrong can invert efficiency definitions.

### 3.2 Capacity-Activity Relationship

If PCG includes multiple commodities (e.g., CHP with electricity + heat):
- Activity = sum of PCG flows
- Capacity relates to this sum, not individual flows
- Peak contribution becomes flow-based, not capacity-based

### 3.3 Shadow Primary Group (SPG)

The SPG is automatically derived as commodities on the opposite side of PCG with the same type. Wrong PCG → wrong SPG → wrong flow constraints.

## 4. Recommended Approach for VedaLang

**Recommendation: Option C - Auto-compute at compile time with optional override**

### Rationale

1. **Most processes have obvious PCG**: A single-fuel power plant producing electricity has NRG outputs → `NRGO` is obvious
2. **xl2times inference is deterministic**: Same rules can be applied at VedaLang compile time
3. **Explicit override when needed**: CHP, multi-product processes, unusual topologies need explicit specification
4. **Transparency**: VedaLang compiler can report inferred PCG in diagnostics/comments

### Schema Addition

```json
"process": {
  "properties": {
    "primary_commodity_group": {
      "type": "string",
      "enum": ["DEMI", "DEMO", "MATI", "MATO", "NRGI", "NRGO", "ENVI", "ENVO", "FINI", "FINO"],
      "description": "Primary commodity group. If omitted, inferred from topology (first NRG output, etc.)"
    }
  }
}
```

### Compiler Behavior

1. If `primary_commodity_group` is specified: use it directly
2. If omitted: apply xl2times inference logic at compile time
3. Either way: **always emit `primarycg` column in ~FI_PROCESS**

This makes VedaLang explicit (the column is always present) while keeping simple cases simple (inference handles the common patterns).

## 5. Implementation Spec

### 5.1 Schema Changes

Add to process definition in `vedalang.schema.json`:

```json
"primary_commodity_group": {
  "type": "string", 
  "enum": ["DEMI", "DEMO", "MATI", "MATO", "NRGI", "NRGO", "ENVI", "ENVO", "FINI", "FINO"],
  "description": "Primary commodity group. Controls activity definition. If omitted, inferred from topology."
}
```

### 5.2 Compiler Changes

In `compile_to_tableir()`:

```python
def _infer_pcg(process: dict, commodities: dict[str, dict]) -> str:
    """Infer PCG using xl2times rules."""
    csets_order = ["DEM", "MAT", "NRG", "ENV", "FIN"]
    
    # Build lookup: commodity_name -> csets
    comm_types = {c["name"]: _commodity_type_to_csets(c.get("type", "energy")) 
                  for c in commodities}
    
    # Try outputs first, then inputs
    for io, flow_key in [("O", "outputs"), ("I", "inputs")]:
        flows = process.get(flow_key, [])
        for cset in csets_order:
            for flow in flows:
                if comm_types.get(flow["commodity"]) == cset:
                    return cset + io
    
    return "NRGO"  # Fallback default
```

Add to process row emission:

```python
for process in model.get("processes", []):
    pcg = process.get("primary_commodity_group") or _infer_pcg(process, commodities_by_name)
    process_rows.append({
        "region": default_region,
        "techname": process["name"],
        "techdesc": process.get("description", ""),
        "sets": ",".join(process.get("sets", [])),
        "tact": process.get("activity_unit", "PJ"),
        "tcap": process.get("capacity_unit", "GW"),
        "primarycg": pcg,  # NEW: always emit
    })
```

### 5.3 Test Cases

1. **Simple plant (inference)**: Gas plant with NRG input/output → infers `NRGO`
2. **Demand device (inference)**: Heater with NRG input, DEM output → infers `DEMO`
3. **Explicit override**: CHP with explicit `primary_commodity_group: "NRGO"`
4. **Multi-output (inference)**: Refinery with multiple NRG outputs → infers `NRGO`

## 6. Implementation Status

**Status: SPEC COMPLETE, IMPLEMENTATION PENDING**

The implementation is straightforward (~50 lines of code) but should be done in a separate commit with tests.

### Next Steps

1. Create issue for implementation tracking
2. Add schema field (5 mins)
3. Implement `_infer_pcg()` function (15 mins)
4. Update process emission to include `primarycg` (5 mins)
5. Add test cases (20 mins)
6. Update mini_plant.veda.yaml example (5 mins)
