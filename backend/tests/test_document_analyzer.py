"""Tests for document analyzer JSON validation and repair retry."""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture
def openai_client(settings: Settings) -> OpenAIClient:
    """Create mock OpenAI client."""
    return OpenAIClient(settings)


@pytest.fixture
def document_analyzer(settings: Settings, openai_client: OpenAIClient) -> DocumentAnalyzer:
    """Create document analyzer."""
    return DocumentAnalyzer(settings, openai_client)


def test_invalid_json_triggers_repair_retry(
    document_analyzer: DocumentAnalyzer,
) -> None:
    """Test that invalid JSON triggers a repair retry."""
    # Create mock PDF page images
    pdf_images = [
        PdfPageImage(
            page_number=1,
            image_base64="dGVzdA==",  # base64 for "test"
            mime_type="image/png",
        )
    ]

    # Mock OpenAI client to return invalid JSON first, then valid JSON
    with patch.object(
        document_analyzer.openai_client,
        "call_vision",
        side_effect=[
            "This is not valid JSON at all",
            json.dumps({
                "project_type": "row_house",
                "scope_type": "repair",
                "sheets": [],
                "where_scope_lives": [],
                "where_quantities_live": [],
                "where_materials_live": [],
                "building_context": None,
                "key_dimensions": None,
                "critical_expected_items": [],
                "confidence": 0.8,
                "missing_fields": [],
            }),
        ],
    ):
        result = document_analyzer.analyze(pdf_images, "test-project-id")
        assert isinstance(result, DocumentAnalysis)
        assert result.project_type == "row_house"
        assert result.scope_type == "repair"


def test_invalid_json_after_max_retries_raises_error(
    document_analyzer: DocumentAnalyzer,
) -> None:
    """Test that invalid JSON after max retries raises ValueError."""
    pdf_images = [
        PdfPageImage(
            page_number=1,
            image_base64="dGVzdA==",
            mime_type="image/png",
        )
    ]

    # Mock OpenAI client to always return invalid JSON
    with patch.object(
        document_analyzer.openai_client,
        "call_vision",
        return_value="Still not valid JSON",
    ):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            document_analyzer.analyze(pdf_images, "test-project-id")


def test_invalid_schema_raises_validation_error(
    document_analyzer: DocumentAnalyzer,
) -> None:
    """Test that JSON that doesn't match schema raises ValidationError."""
    pdf_images = [
        PdfPageImage(
            page_number=1,
            image_base64="dGVzdA==",
            mime_type="image/png",
        )
    ]

    # Mock OpenAI client to return valid JSON but invalid schema
    invalid_json = {
        "project_type": "invalid_type",  # Invalid enum value
        "scope_type": "repair",
        "sheets": [],
        "where_scope_lives": [],
        "where_quantities_live": [],
        "where_materials_live": [],
        "building_context": None,
        "key_dimensions": None,
        "critical_expected_items": [],
        "confidence": 0.8,
        "missing_fields": [],
    }

    with patch.object(
        document_analyzer.openai_client,
        "call_vision",
        return_value=json.dumps(invalid_json),
    ):
        with pytest.raises(ValueError, match="does not match DocumentAnalysis schema"):
            document_analyzer.analyze(pdf_images, "test-project-id")


def test_valid_response_returns_document_analysis(
    document_analyzer: DocumentAnalyzer,
) -> None:
    """Test that valid JSON response returns DocumentAnalysis."""
    pdf_images = [
        PdfPageImage(
            page_number=1,
            image_base64="dGVzdA==",
            mime_type="image/png",
        )
    ]

    valid_json = {
        "project_type": "row_house",
        "scope_type": "repair",
        "sheets": [
            {
                "sheet_id": "A-1",
                "page_number": 1,
                "sheet_type": "elevation",
                "title": "Front Elevation",
            }
        ],
        "where_scope_lives": [
            {
                "sheet_id": "A-1",
                "page_number": 1,
                "location_type": "elevation_notes",
                "evidence": "Parapet repair noted",
                "confidence": 0.9,
            }
        ],
        "where_quantities_live": [],
        "where_materials_live": [],
        "building_context": {
            "building_type": "row_house",
            "is_row_context": True,
            "building_ids": ["B-1"],
            "addresses": [],
            "evidence": "Row of attached buildings visible",
        },
        "key_dimensions": None,
        "critical_expected_items": [
            {
                "item": "parapet",
                "expected_for": "row_house_repair",
                "found": True,
                "evidence": "Parapet repair noted on elevation",
                "confidence": 0.9,
            }
        ],
        "confidence": 0.85,
        "missing_fields": ["key_dimensions"],
    }

    with patch.object(
        document_analyzer.openai_client,
        "call_vision",
        return_value=json.dumps(valid_json),
    ):
        result = document_analyzer.analyze(pdf_images, "test-project-id")
        assert isinstance(result, DocumentAnalysis)
        assert result.project_type == "row_house"
        assert result.scope_type == "repair"
        assert len(result.sheets) == 1
        assert len(result.where_scope_lives) == 1
        assert result.building_context is not None
        assert result.building_context.is_row_context is True

