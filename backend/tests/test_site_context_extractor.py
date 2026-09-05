"""Unit tests for site context extractor (Task 3)."""

import pytest

from app.schemas.document_analysis import BuildingContext, DocumentAnalysis
from app.schemas.site_context import SiteContext
from app.services.site_context_extractor import (
    extract_site_context_from_analysis,
    extract_site_context_from_text,
)


def test_extract_site_context_evidence_attached():
    """Test extracting row_condition from evidence."""
    text = "ROW HOUSE - PARTY WALL to adjacent buildings. Typical adjacent building shown."
    context = extract_site_context_from_text(text, is_row_house=True)

    assert context.row_condition == "attached"
    assert context.provenance.row_condition == "evidence"


def test_extract_site_context_inferred_attached():
    """Test inferring row_condition when party wall indicators present."""
    text = "Repair work on typical adjacent building conditions"
    context = extract_site_context_from_text(text, is_row_house=True)

    assert context.row_condition == "attached"
    assert context.provenance.row_condition == "inferred"


def test_extract_site_context_no_guess_neighbor_addresses():
    """Test that neighbor addresses are never invented."""
    text = "123 Main Street - Row house repair"
    context = extract_site_context_from_text(text, is_row_house=True)

    # Should extract street_front from subject address
    assert context.street_front is not None
    assert context.provenance.street_front == "evidence"
    # Should NOT invent cross streets or neighbor addresses
    assert context.cross_street_left is None or context.provenance.cross_street_left == "unknown"
    assert context.cross_street_right is None or context.provenance.cross_street_right == "unknown"


def test_extract_site_context_evidence_cross_streets():
    """Test extracting cross streets from evidence."""
    text = "Building located at corner of Main Street and Oak Avenue"
    context = extract_site_context_from_text(text, is_row_house=True)

    assert context.cross_street_left is not None or context.cross_street_right is not None
    # At least one cross street should be evidence
    assert (
        context.provenance.cross_street_left == "evidence"
        or context.provenance.cross_street_right == "evidence"
    )


def test_extract_site_context_row_count_evidence():
    """Test extracting row count from building IDs (evidence)."""
    text = "Buildings B-1, B-2, B-3 shown. Subject building is B-2."
    context = extract_site_context_from_text(text, is_row_house=True)

    assert context.row_count_estimate == 3
    assert context.provenance.row_count_estimate == "evidence"
    assert context.subject_position == "middle"
    assert context.provenance.subject_position == "evidence"


def test_extract_site_context_row_count_inferred():
    """Test inferring row count from TYP. ADJ. BLDG."""
    text = "TYP. ADJ. BLDG conditions apply"
    context = extract_site_context_from_text(text, is_row_house=True)

    assert context.row_count_estimate == 3  # Subject + 2 adjacent
    assert context.provenance.row_count_estimate == "inferred"


def test_extract_site_context_from_analysis():
    """Test extracting site context from DocumentAnalysis."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        building_context=BuildingContext(
            building_type="row_house",
            is_row_context=True,
            building_ids=["B-1", "B-2"],
            addresses=["123 Main Street"],
            evidence="Row house with party walls",
        ),
        sheets=[],
        where_scope_lives=[],
        where_quantities_lives=[],
        where_materials_lives=[],
        critical_expected_items=[],
        confidence=0.9,
        missing_fields=[],
    )

    context = extract_site_context_from_analysis(analysis)

    assert isinstance(context, SiteContext)
    assert context.row_condition in ["attached", "unknown"]
    # Should extract street from address
    assert context.street_front is not None or context.provenance.street_front == "unknown"


def test_extract_site_context_all_fields_have_provenance():
    """Test that all fields have provenance tracking."""
    text = "123 Main Street - Row house repair with party walls"
    context = extract_site_context_from_text(text, is_row_house=True)

    # All provenance fields should be set
    assert context.provenance.street_front in ["evidence", "inferred", "unknown"]
    assert context.provenance.cross_street_left in ["evidence", "inferred", "unknown"]
    assert context.provenance.cross_street_right in ["evidence", "inferred", "unknown"]
    assert context.provenance.row_condition in ["evidence", "inferred", "unknown"]
    assert context.provenance.row_count_estimate in ["evidence", "inferred", "unknown"]
    assert context.provenance.subject_position in ["evidence", "inferred", "unknown"]





