"""Tests for labor breakdown schema (Phase 9.3A)."""

from datetime import datetime

import pytest

from app.schemas.labor_breakdown import LaborActivity, LaborBreakdown


def test_labor_activity_construction() -> None:
    """Test constructing a LaborActivity with all fields."""
    activity = LaborActivity(
        activity_id="parapet_rebuild_001",
        title="Parapet Rebuild",
        related_bid_item_ids=["bid_item_001", "bid_item_002"],
        quantity=50.0,
        unit="LF",
        productivity_per_day=10.0,
        crew=["mason", "laborer"],
        estimated_days=5.0,
        labor_cost=4250.0,
        reason="From bid item: Parapet rebuild, 50 LF",
        confidence=0.9,
    )

    assert activity.activity_id == "parapet_rebuild_001"
    assert activity.title == "Parapet Rebuild"
    assert len(activity.related_bid_item_ids) == 2
    assert activity.quantity == 50.0
    assert activity.unit == "LF"
    assert activity.productivity_per_day == 10.0
    assert activity.crew == ["mason", "laborer"]
    assert activity.estimated_days == 5.0
    assert activity.labor_cost == 4250.0
    assert activity.reason == "From bid item: Parapet rebuild, 50 LF"
    assert activity.confidence == 0.9


def test_labor_activity_minimal() -> None:
    """Test constructing a LaborActivity with minimal required fields."""
    activity = LaborActivity(
        activity_id="repointing_001",
        title="Brick Repointing",
        quantity=500.0,
        unit="SF",
        reason="From bid item: Brick repointing",
        confidence=0.8,
    )

    assert activity.activity_id == "repointing_001"
    assert activity.title == "Brick Repointing"
    assert activity.quantity == 500.0
    assert activity.unit == "SF"
    assert activity.related_bid_item_ids == []
    assert activity.productivity_per_day is None
    assert activity.crew == []
    assert activity.estimated_days is None
    assert activity.labor_cost is None
    assert activity.confidence == 0.8


def test_labor_activity_confidence_bounds() -> None:
    """Test that confidence must be between 0 and 1."""
    # Valid confidence values
    activity1 = LaborActivity(
        activity_id="test_001",
        title="Test Activity",
        quantity=10.0,
        unit="each",
        reason="Test",
        confidence=0.0,
    )
    assert activity1.confidence == 0.0

    activity2 = LaborActivity(
        activity_id="test_002",
        title="Test Activity",
        quantity=10.0,
        unit="each",
        reason="Test",
        confidence=1.0,
    )
    assert activity2.confidence == 1.0

    # Invalid confidence values should raise validation error
    with pytest.raises(Exception):  # Pydantic validation error
        LaborActivity(
            activity_id="test_003",
            title="Test Activity",
            quantity=10.0,
            unit="each",
            reason="Test",
            confidence=1.5,  # > 1.0
        )

    with pytest.raises(Exception):  # Pydantic validation error
        LaborActivity(
            activity_id="test_004",
            title="Test Activity",
            quantity=10.0,
            unit="each",
            reason="Test",
            confidence=-0.1,  # < 0.0
        )


def test_labor_activity_quantity_bounds() -> None:
    """Test that quantity must be >= 0."""
    activity = LaborActivity(
        activity_id="test_001",
        title="Test Activity",
        quantity=0.0,
        unit="each",
        reason="Test",
        confidence=0.9,
    )
    assert activity.quantity == 0.0

    with pytest.raises(Exception):  # Pydantic validation error
        LaborActivity(
            activity_id="test_002",
            title="Test Activity",
            quantity=-10.0,  # < 0.0
            unit="each",
            reason="Test",
            confidence=0.9,
        )


def test_labor_breakdown_construction() -> None:
    """Test constructing a LaborBreakdown with multiple activities."""
    activities = [
        LaborActivity(
            activity_id="parapet_001",
            title="Parapet Rebuild",
            quantity=50.0,
            unit="LF",
            productivity_per_day=10.0,
            crew=["mason", "laborer"],
            estimated_days=5.0,
            labor_cost=4250.0,
            reason="From bid item: Parapet rebuild",
            confidence=0.9,
        ),
        LaborActivity(
            activity_id="repointing_001",
            title="Brick Repointing",
            quantity=500.0,
            unit="SF",
            productivity_per_day=120.0,
            crew=["mason", "laborer"],
            estimated_days=4.17,
            labor_cost=3545.0,
            reason="From bid item: Brick repointing",
            confidence=0.9,
        ),
    ]

    breakdown = LaborBreakdown(
        project_id="test_project_123",
        profile_id="nyc_row_house_masonry_v1",
        activities=activities,
        total_labor_cost=7795.0,
    )

    assert breakdown.project_id == "test_project_123"
    assert breakdown.profile_id == "nyc_row_house_masonry_v1"
    assert len(breakdown.activities) == 2
    assert breakdown.activities[0].title == "Parapet Rebuild"
    assert breakdown.activities[1].title == "Brick Repointing"
    assert breakdown.total_labor_cost == 7795.0
    assert isinstance(breakdown.created_at, datetime)


def test_labor_breakdown_empty_activities() -> None:
    """Test LaborBreakdown with no activities (empty list)."""
    breakdown = LaborBreakdown(
        project_id="test_project_456",
        profile_id="nyc_row_house_masonry_v1",
        activities=[],
        total_labor_cost=0.0,
    )

    assert breakdown.project_id == "test_project_456"
    assert breakdown.profile_id == "nyc_row_house_masonry_v1"
    assert len(breakdown.activities) == 0
    assert breakdown.total_labor_cost == 0.0


def test_labor_breakdown_total_cost_calculation() -> None:
    """Test that total_labor_cost can be calculated from activities."""
    activities = [
        LaborActivity(
            activity_id="activity_001",
            title="Activity 1",
            quantity=10.0,
            unit="each",
            labor_cost=1000.0,
            reason="Test",
            confidence=0.9,
        ),
        LaborActivity(
            activity_id="activity_002",
            title="Activity 2",
            quantity=20.0,
            unit="each",
            labor_cost=2000.0,
            reason="Test",
            confidence=0.9,
        ),
    ]

    breakdown = LaborBreakdown(
        project_id="test_project",
        profile_id="nyc_row_house_masonry_v1",
        activities=activities,
        total_labor_cost=3000.0,  # Sum of activity costs
    )

    assert breakdown.total_labor_cost == 3000.0
    # Verify it matches sum
    calculated_total = sum(act.labor_cost or 0.0 for act in breakdown.activities)
    assert calculated_total == breakdown.total_labor_cost






