"""Tests for region resolver (Phase 9.7)."""

import pytest

from app.services.region_resolver import resolve_region, select_profile_id


def test_resolve_region_from_address_nyc():
    """Test region resolution from NYC address."""
    document_analysis = {
        "project_address": "123 Main St, Queens, NY 11385",
        "text_blocks": [],
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "NYC"
    assert result["confidence"] > 0.7
    assert len(result["evidence"]) > 0
    assert "Queens" in result["evidence"][0] or "NY" in result["evidence"][0]


def test_resolve_region_from_zipcode_nyc():
    """Test region resolution from NYC zipcode."""
    document_analysis = {
        "text_blocks": [
            {"text": "Project located at 12345 Broadway, New York, NY 10001"}
        ],
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "NYC"
    assert result["confidence"] > 0.7


def test_resolve_region_from_nj_address():
    """Test region resolution from New Jersey address."""
    document_analysis = {
        "project_address": "456 Oak Ave, Newark, NJ 07102",
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "NJ"
    assert result["confidence"] > 0.7


def test_resolve_region_from_tx_address():
    """Test region resolution from Texas address."""
    document_analysis = {
        "project_location": "Dallas, TX 75201",
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "TX"
    assert result["confidence"] > 0.7


def test_resolve_region_from_dob_reference():
    """Test region resolution from DOB/NYC references."""
    document_analysis = {
        "text_blocks": [
            {"text": "DOB permit required for this project in NYC"}
        ],
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "NYC"
    assert result["confidence"] >= 0.7


def test_resolve_region_no_signals():
    """Test region resolution with no location signals."""
    document_analysis = {
        "text_blocks": [{"text": "General construction project"}],
    }
    
    result = resolve_region(document_analysis=document_analysis)
    
    assert result["region_id"] == "US_DEFAULT"
    assert result["confidence"] == 0.0
    assert "No location signals found" in result["evidence"][0]


def test_resolve_region_from_extraction_result():
    """Test region resolution from extraction result."""
    extraction_result = {
        "project_location": "Philadelphia, PA 19102",
    }
    
    result = resolve_region(extraction_result=extraction_result)
    
    assert result["region_id"] == "PA"
    assert result["confidence"] > 0.7


def test_select_profile_id_nyc():
    """Test profile selection for NYC."""
    profile_id = select_profile_id("NYC", "row_house_masonry")
    assert profile_id == "nyc_row_house_masonry_v1"


def test_select_profile_id_nj():
    """Test profile selection for NJ."""
    profile_id = select_profile_id("NJ", "row_house_masonry")
    assert profile_id == "nj_row_house_masonry_v1"


def test_select_profile_id_tx():
    """Test profile selection for TX."""
    profile_id = select_profile_id("TX", "row_house_masonry")
    assert profile_id == "tx_row_house_masonry_v1"


def test_select_profile_id_default():
    """Test profile selection for default region."""
    profile_id = select_profile_id("US_DEFAULT", "row_house_masonry")
    assert profile_id == "us_default_v1"


def test_select_profile_id_unknown_region():
    """Test profile selection for unknown region falls back to default."""
    profile_id = select_profile_id("UNKNOWN", "row_house_masonry")
    assert profile_id == "us_default_v1"






