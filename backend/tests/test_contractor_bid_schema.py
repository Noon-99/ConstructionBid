"""Tests for contractor bid schema (Phase 9.4A)."""

from datetime import datetime

import pytest

from app.schemas.contractor_bid import (
    ContractorBid,
    ContractorBidLineItem,
    ContractorBidSection,
    ContractorSchedule,
    PaymentMilestone,
)


def test_contractor_bid_line_item_construction() -> None:
    """Test constructing a ContractorBidLineItem."""
    item = ContractorBidLineItem(
        item_id="item_001",
        title="Parapet Rebuild",
        division="04",
        quantity=50.0,
        unit="LF",
        unit_cost=150.0,
        total_cost=7500.0,
        basis="From drawings",
        notes="Includes flashing and waterproofing",
    )

    assert item.item_id == "item_001"
    assert item.title == "Parapet Rebuild"
    assert item.division == "04"
    assert item.quantity == 50.0
    assert item.unit == "LF"
    assert item.unit_cost == 150.0
    assert item.total_cost == 7500.0
    assert item.basis == "From drawings"
    assert item.notes == "Includes flashing and waterproofing"


def test_contractor_bid_line_item_lump_sum() -> None:
    """Test ContractorBidLineItem as lump sum (no quantity/unit)."""
    item = ContractorBidLineItem(
        item_id="item_002",
        title="Permit Filing",
        division="01",
        quantity=None,
        unit=None,
        unit_cost=None,
        total_cost=2500.0,
        basis="NYC DOB requirements",
    )

    assert item.quantity is None
    assert item.unit is None
    assert item.unit_cost is None
    assert item.total_cost == 2500.0


def test_contractor_bid_section_construction() -> None:
    """Test constructing a ContractorBidSection."""
    line_items = [
        ContractorBidLineItem(
            item_id="item_001",
            title="Parapet Rebuild",
            division="04",
            quantity=50.0,
            unit="LF",
            unit_cost=150.0,
            total_cost=7500.0,
            basis="From drawings",
        ),
        ContractorBidLineItem(
            item_id="item_002",
            title="Brick Repointing",
            division="04",
            quantity=500.0,
            unit="SF",
            unit_cost=8.0,
            total_cost=4000.0,
            basis="From drawings",
        ),
    ]

    section = ContractorBidSection(
        section_id="section_001",
        title="Masonry Work",
        division="04",
        line_items=line_items,
        subtotal=11500.0,
    )

    assert section.section_id == "section_001"
    assert section.title == "Masonry Work"
    assert section.division == "04"
    assert len(section.line_items) == 2
    assert section.subtotal == 11500.0


def test_contractor_schedule_construction() -> None:
    """Test constructing a ContractorSchedule."""
    schedule = ContractorSchedule(
        estimated_start_date="2025-03-01",
        estimated_duration_days=60,
        estimated_completion_date="2025-04-30",
        phases=[],
    )

    assert schedule.estimated_start_date == "2025-03-01"
    assert schedule.estimated_duration_days == 60
    assert schedule.estimated_completion_date == "2025-04-30"
    assert schedule.phases == []


def test_payment_milestone_construction() -> None:
    """Test constructing a PaymentMilestone."""
    milestone = PaymentMilestone(
        milestone_id="milestone_001",
        title="Mobilization",
        percentage=10.0,
        amount=5000.0,
        trigger="Upon mobilization and site setup",
    )

    assert milestone.milestone_id == "milestone_001"
    assert milestone.title == "Mobilization"
    assert milestone.percentage == 10.0
    assert milestone.amount == 5000.0
    assert milestone.trigger == "Upon mobilization and site setup"


def test_payment_milestone_percentage_bounds() -> None:
    """Test that payment milestone percentage must be between 0 and 100."""
    milestone = PaymentMilestone(
        milestone_id="milestone_001",
        title="Test",
        percentage=50.0,
        amount=25000.0,
        trigger="Test trigger",
    )
    assert milestone.percentage == 50.0

    with pytest.raises(Exception):  # Pydantic validation error
        PaymentMilestone(
            milestone_id="milestone_002",
            title="Test",
            percentage=150.0,  # > 100.0
            amount=25000.0,
            trigger="Test trigger",
        )

    with pytest.raises(Exception):  # Pydantic validation error
        PaymentMilestone(
            milestone_id="milestone_003",
            title="Test",
            percentage=-10.0,  # < 0.0
            amount=25000.0,
            trigger="Test trigger",
        )


def test_contractor_bid_construction() -> None:
    """Test constructing a ContractorBid with all fields."""
    sections = [
        ContractorBidSection(
            section_id="section_001",
            title="Masonry Work",
            division="04",
            line_items=[
                ContractorBidLineItem(
                    item_id="item_001",
                    title="Parapet Rebuild",
                    division="04",
                    quantity=50.0,
                    unit="LF",
                    unit_cost=150.0,
                    total_cost=7500.0,
                    basis="From drawings",
                ),
            ],
            subtotal=7500.0,
        ),
    ]

    permits = [
        ContractorBidLineItem(
            item_id="permit_001",
            title="Permit Filing",
            division="01",
            quantity=None,
            unit=None,
            unit_cost=None,
            total_cost=2500.0,
            basis="NYC DOB requirements",
        ),
    ]

    logistics = [
        ContractorBidLineItem(
            item_id="logistics_001",
            title="Scaffolding",
            division="01",
            quantity=6.0,
            unit="week",
            unit_cost=1200.0,
            total_cost=7200.0,
            basis="Required for exterior work",
        ),
    ]

    payment_schedule = [
        PaymentMilestone(
            milestone_id="milestone_001",
            title="Mobilization",
            percentage=10.0,
            amount=1720.0,
            trigger="Upon mobilization",
        ),
    ]

    bid = ContractorBid(
        project_id="test_project",
        bid_mode="contractor",
        total_bid=17200.0,
        subtotals={"scope": 7500.0, "permits": 2500.0, "logistics": 7200.0},
        sections=sections,
        schedule=ContractorSchedule(
            estimated_start_date="2025-03-01",
            estimated_duration_days=60,
        ),
        payment_schedule=payment_schedule,
        permits_and_inspections=permits,
        logistics=logistics,
        exclusions=["Site work not shown on drawings", "Interior finishes"],
        assumptions=["Access to site available", "No hazardous materials"],
    )

    assert bid.project_id == "test_project"
    assert bid.bid_mode == "contractor"
    assert bid.total_bid == 17200.0
    assert len(bid.sections) == 1
    assert len(bid.permits_and_inspections) == 1
    assert len(bid.logistics) == 1
    assert len(bid.exclusions) == 2
    assert len(bid.assumptions) == 2
    assert bid.schedule is not None
    assert bid.payment_schedule is not None
    assert isinstance(bid.created_at, datetime)


def test_contractor_bid_minimal() -> None:
    """Test constructing a ContractorBid with minimal required fields."""
    bid = ContractorBid(
        project_id="test_project",
        bid_mode="contractor",
        total_bid=0.0,
        subtotals={},
        sections=[],
    )

    assert bid.project_id == "test_project"
    assert bid.bid_mode == "contractor"
    assert bid.total_bid == 0.0
    assert len(bid.sections) == 0
    assert bid.schedule is None
    assert bid.payment_schedule is None
    assert len(bid.permits_and_inspections) == 0
    assert len(bid.logistics) == 0
    assert len(bid.exclusions) == 0
    assert len(bid.assumptions) == 0






