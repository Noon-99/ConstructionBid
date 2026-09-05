"""Tests for proposal template engine (Phase 9.8)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidAllowance, BidClarification, BidLineItem, BidProposal, BidSummary
from app.schemas.contractor_bid import ContractorBid, ContractorBidLineItem, ContractorBidSection
from app.services.proposal_template_engine import render_contractor_proposal_markdown


@pytest.fixture
def settings():
    """Test settings."""
    return Settings()


@pytest.fixture
def sample_bid_proposal():
    """Create a sample bid proposal for fallback testing."""
    return BidProposal(
        project_id="test-project-123",
        summary=BidSummary(
            total_cost=50000.0,
            cost_by_division={"04 Masonry": 40000.0, "01 General": 10000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Parapet rebuild",
                quantity=50.0,
                unit="LF",
                unit_cost=150.0,
                total_cost=7500.0,
                basis="From drawings",
                confidence=0.9,
            ),
            BidLineItem(
                division="04 Masonry",
                description="Brick repointing",
                quantity=500.0,
                unit="SF",
                unit_cost=8.0,
                total_cost=4000.0,
                basis="From drawings",
                confidence=0.9,
            ),
        ],
        allowances=[
            BidAllowance(name="Permits", amount=2500.0, notes="NYC building permit"),
        ],
        clarifications=[
            BidClarification(
                text="Review parapet condition on site", severity="warning"
            ),
        ],
        generated_at="2025-01-01T00:00:00Z",
        estimate_mode="conceptual",
        bid_ready=False,
    )


@pytest.fixture
def sample_contractor_bid():
    """Create a sample contractor bid."""
    return ContractorBid(
        project_id="test-project-456",
        bid_mode="contractor",
        total_bid=75000.0,
        subtotals={
            "base_scope": 50000.0,
            "logistics": 10000.0,
            "permits": 5000.0,
            "labor": 8000.0,
            "overhead": 9000.0,
            "profit": 6000.0,
            "contingency": 5000.0,
        },
        sections=[
            ContractorBidSection(
                section_id="base_scope",
                title="Base Scope (from drawings)",
                division=None,
                line_items=[
                    ContractorBidLineItem(
                        item_id="item-1",
                        title="Parapet rebuild",
                        division="04",
                        quantity=50.0,
                        unit="LF",
                        unit_cost=150.0,
                        total_cost=7500.0,
                        basis="From drawings",
                        notes=None,
                    ),
                ],
                subtotal=7500.0,
            ),
        ],
        permits_and_inspections=[
            ContractorBidLineItem(
                item_id="perm-1",
                title="Building Permit",
                division=None,
                quantity=None,
                unit=None,
                unit_cost=None,
                total_cost=2500.0,
                basis="NYC permit fees",
                notes=None,
            ),
        ],
        logistics=[
            ContractorBidLineItem(
                item_id="log-1",
                title="Scaffolding",
                division=None,
                quantity=4.0,
                unit="week",
                unit_cost=1200.0,
                total_cost=4800.0,
                basis="Contractor profile",
                notes=None,
            ),
        ],
        exclusions=["Site work", "Landscaping"],
        assumptions=["Access available", "Weather delays not included"],
        payment_schedule=None,
        schedule=None,
    )


def test_render_contractor_proposal_markdown_with_contractor_bid(
    settings, sample_contractor_bid
):
    """Test rendering markdown from contractor_bid.json."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        # Save contractor_bid.json
        contractor_bid_file = output_dir / "contractor_bid.json"
        with open(contractor_bid_file, "w") as f:
            f.write(sample_contractor_bid.model_dump_json(indent=2))
        
        # Save document_analysis.json
        analysis_file = output_dir / "document_analysis.json"
        with open(analysis_file, "w") as f:
            json.dump(
                {
                    "project_name": "Test Project",
                    "project_address": "123 Main St, NYC",
                },
                f,
            )
        
        # Render markdown
        markdown = render_contractor_proposal_markdown(
            project_id="test-project-456",
            output_dir=output_dir,
            settings=settings,
        )
        
        # Verify content
        assert "Executive Summary" in markdown
        assert "Total Bid Amount" in markdown
        assert "$75,000.00" in markdown
        assert "Base Scope" in markdown
        assert "Parapet rebuild" in markdown
        assert "Scaffolding" in markdown
        assert "Building Permit" in markdown
        assert "Exclusions" in markdown
        assert "Site work" in markdown
        assert "Assumptions" in markdown
        assert "Access available" in markdown


def test_render_contractor_proposal_markdown_fallback_to_bid_proposal(
    settings, sample_bid_proposal
):
    """Test rendering markdown falls back to bid_proposal.json when contractor_bid missing."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        # Save bid_proposal.json (no contractor_bid.json)
        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(sample_bid_proposal.model_dump_json(indent=2))
        
        # Save document_analysis.json
        analysis_file = output_dir / "document_analysis.json"
        with open(analysis_file, "w") as f:
            json.dump(
                {
                    "project_name": "Test Project",
                    "project_address": "123 Main St",
                },
                f,
            )
        
        # Render markdown
        markdown = render_contractor_proposal_markdown(
            project_id="test-project-123",
            output_dir=output_dir,
            settings=settings,
        )
        
        # Verify content
        assert "Executive Summary" in markdown
        assert "Total Bid Amount" in markdown
        assert "$50,000.00" in markdown
        assert "Scope of Work" in markdown
        assert "Parapet rebuild" in markdown
        assert "Brick repointing" in markdown


def test_render_contractor_proposal_markdown_missing_files(settings):
    """Test that rendering raises FileNotFoundError when no bid files exist."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        with pytest.raises(FileNotFoundError):
            render_contractor_proposal_markdown(
                project_id="test-project-789",
                output_dir=output_dir,
                settings=settings,
            )


def test_render_contractor_proposal_markdown_includes_estimated_duration(settings, sample_contractor_bid):
    """Test that estimated duration is included when labor_breakdown exists."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        # Save contractor_bid.json
        contractor_bid_file = output_dir / "contractor_bid.json"
        with open(contractor_bid_file, "w") as f:
            f.write(sample_contractor_bid.model_dump_json(indent=2))
        
        # Save labor_breakdown.json with estimated days
        labor_file = output_dir / "labor_breakdown.json"
        with open(labor_file, "w") as f:
            json.dump(
                {
                    "project_id": "test-project-456",
                    "profile_id": "nyc_row_house_masonry_v1",
                    "activities": [
                        {
                            "activity_id": "activity_001",
                            "title": "Parapet rebuild",
                            "estimated_days": 10.0,
                        },
                        {
                            "activity_id": "activity_002",
                            "title": "Brick repointing",
                            "estimated_days": 15.0,
                        },
                    ],
                    "total_labor_cost": 8000.0,
                },
                f,
            )
        
        # Save document_analysis.json
        analysis_file = output_dir / "document_analysis.json"
        with open(analysis_file, "w") as f:
            json.dump(
                {
                    "project_name": "Test Project",
                    "project_address": "123 Main St",
                },
                f,
            )
        
        # Render markdown
        markdown = render_contractor_proposal_markdown(
            project_id="test-project-456",
            output_dir=output_dir,
            settings=settings,
        )
        
        # Verify estimated duration is included
        assert "Estimated Duration" in markdown or "weeks" in markdown






