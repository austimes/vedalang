"""Tests for IIS/Conflict Refiner parsing in veda_run_times."""

from tools.veda_run_times.runner import parse_gams_listing


def test_iis_parsing_with_conflict_section():
    """Test that IIS info is extracted from CPLEX conflict refiner output."""
    content = """
**** MODEL STATUS      4 INFEASIBLE
**** SOLVER STATUS     1 NORMAL COMPLETION

Conflict Refiner status
Number of equations in conflict:   3
Number of variables in conflict:   2

upper: EQ_DEMAND_RSD(NORTH,2020) < 100
lower: VAR_CAP(PP_CCGT,NORTH) > 0
equality: EQ_BALANCE(ELC,2020) = 0

Other output continues here...
"""
    diag = parse_gams_listing(content)

    assert diag["iis"]["available"] is True
    assert diag["iis"]["counts"]["equations"] == 3
    assert diag["iis"]["counts"]["variables"] == 2
    assert len(diag["iis"]["members"]) == 3

    # Check first member
    assert diag["iis"]["members"][0]["role"] == "upper"
    assert diag["iis"]["members"][0]["symbol"] == "EQ_DEMAND_RSD(NORTH,2020)"

    # Check second member
    assert diag["iis"]["members"][1]["role"] == "lower"
    assert diag["iis"]["members"][1]["symbol"] == "VAR_CAP(PP_CCGT,NORTH)"


def test_iis_not_available_without_conflict():
    """Test that IIS is not available when no conflict refiner output exists."""
    content = """
**** MODEL STATUS      1 OPTIMAL
**** SOLVER STATUS     1 NORMAL COMPLETION
**** OBJECTIVE VALUE   12345.678
"""
    diag = parse_gams_listing(content)

    assert diag["iis"]["available"] is False
    assert diag["iis"]["counts"]["equations"] is None
    assert len(diag["iis"]["members"]) == 0


def test_iis_with_sos_and_indicator():
    """Test parsing of SOS and indicator constraints in IIS."""
    content = """
Conflict Refiner status
Number of equations in conflict:   1
Number of variables in conflict:   1
Number of SOS sets in conflict:   2
Number of indicator constraints in conflict:   1

lower: VAR_X > 0
sos: SOS_SET1
indic: EQ_IND$b 0
"""
    diag = parse_gams_listing(content)

    assert diag["iis"]["available"] is True
    assert diag["iis"]["counts"]["equations"] == 1
    assert diag["iis"]["counts"]["variables"] == 1
    assert diag["iis"]["counts"]["sos_sets"] == 2
    assert diag["iis"]["counts"]["indicator_constraints"] == 1

    roles = [m["role"] for m in diag["iis"]["members"]]
    assert "lower" in roles
    assert "sos" in roles
    assert "indic" in roles
