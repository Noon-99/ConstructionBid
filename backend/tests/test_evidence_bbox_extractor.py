"""Unit tests for evidence bbox extractor (Phase 8.6D)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.evidence_bbox_index import EvidenceBboxEntry, EvidenceBboxIndex
from app.schemas.evidence_index import EvidenceIndex, EvidenceReference, BidItemEvidence
from app.services.evidence_bbox_extractor import EvidenceBboxExtractor


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.enable_ocr_bbox_extraction = False
    return settings


@pytest.fixture
def mock_storage_service(tmp_path):
    """Mock storage service."""
    storage = MagicMock()
    storage.get_source_pdf_path = MagicMock(return_value=tmp_path / "test.pdf")
    return storage


@pytest.fixture
def sample_evidence_index():
    """Sample evidence index for testing."""
    return EvidenceIndex(
        project_id="test_project",
        bid_item_evidence=[
            BidItemEvidence(
                line_item_index=0,
                division="04",
                description="Masonry repair",
                evidence_references=[
                    EvidenceReference(
                        page_number=1,
                        evidence_snippet="Masonry repair required",
                        sheet_id="A-1",
                    )
                ],
                basis="From drawing",
            )
        ],
        zone_evidence=[],
        detail_evidence=[],
        generated_at="2024-01-01T00:00:00",
    )


def test_bbox_extractor_initialization(mock_settings, mock_storage_service):
    """Test bbox extractor initialization."""
    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)
    assert extractor.settings == mock_settings
    assert extractor.storage_service == mock_storage_service
    assert extractor.enable_ocr is False


def test_generate_without_pdf(mock_settings, mock_storage_service, sample_evidence_index):
    """Test bbox extraction when PDF doesn't exist."""
    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)
    result = extractor.generate("test_project", sample_evidence_index)

    assert result.project_id == "test_project"
    assert len(result.entries) == 0
    assert result.metrics["bbox_match_rate"] == 0.0
    assert result.metrics["total_evidence"] == 0


def test_generate_with_pdf_no_match(mock_settings, mock_storage_service, sample_evidence_index, tmp_path):
    """Test bbox extraction when PDF exists but no matches found."""
    # Create a minimal PDF (this would normally be a real PDF)
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()  # Placeholder - in real test would create actual PDF

    mock_storage_service.get_source_pdf_path.return_value = pdf_path

    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)

    # Mock fitz.open to raise exception (simulating invalid PDF)
    with patch("app.services.evidence_bbox_extractor.fitz") as mock_fitz:
        mock_fitz.open.side_effect = Exception("Invalid PDF")

        result = extractor.generate("test_project", sample_evidence_index)

        assert result.project_id == "test_project"
        assert len(result.entries) == 0
        assert result.metrics.get("total_evidence") == 0 or "error" in result.metrics


def test_text_similarity_calculation(mock_settings, mock_storage_service):
    """Test text similarity calculation."""
    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)

    # Exact match
    score = extractor._calculate_text_similarity("masonry repair", "masonry repair")
    assert score == 1.0

    # Substring match (text1 in text2)
    score = extractor._calculate_text_similarity("masonry", "masonry repair required")
    assert score == 1.0  # Substring match returns 1.0

    # Token overlap (Jaccard similarity)
    score = extractor._calculate_text_similarity("masonry repair", "repair masonry work")
    assert score > 0.0
    assert score < 1.0

    # No match
    score = extractor._calculate_text_similarity("masonry", "concrete")
    assert score == 0.0


def test_rect_to_normalized_bbox(mock_settings, mock_storage_service):
    """Test rect to normalized bbox conversion."""
    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)

    # Mock page with known dimensions
    mock_page = MagicMock()
    mock_page.rect.width = 100.0
    mock_page.rect.height = 200.0

    # Mock rect
    mock_rect = MagicMock()
    mock_rect.x0 = 10.0
    mock_rect.y0 = 20.0
    mock_rect.x1 = 30.0
    mock_rect.y1 = 40.0

    bbox = extractor._rect_to_normalized_bbox(mock_rect, mock_page)

    assert bbox["x0"] == 0.1  # 10/100
    assert bbox["y0"] == 0.1  # 20/200
    assert bbox["x1"] == 0.3  # 30/100
    assert bbox["y1"] == 0.2  # 40/200

    # Test clamping to 0-1
    mock_rect.x0 = -10.0
    mock_rect.x1 = 150.0
    bbox = extractor._rect_to_normalized_bbox(mock_rect, mock_page)
    assert bbox["x0"] == 0.0
    assert bbox["x1"] == 1.0


def test_deterministic_output(mock_settings, mock_storage_service, sample_evidence_index):
    """Test that same input produces same output (deterministic)."""
    extractor = EvidenceBboxExtractor(mock_settings, mock_storage_service)

    # This test would require a real PDF file
    # For now, we test that the structure is consistent
    result1 = extractor.generate("test_project", sample_evidence_index)
    result2 = extractor.generate("test_project", sample_evidence_index)

    # Both should have same structure (even if no matches)
    assert result1.project_id == result2.project_id
    assert len(result1.entries) == len(result2.entries)

