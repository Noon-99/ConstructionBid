"""Unit tests for evidence indexer (Phase 6.7)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.evidence_indexer import generate_evidence_index, save_evidence_index
from app.schemas.evidence_index import EvidenceIndex


def test_generate_evidence_index_links_bid_items_to_evidence() -> None:
    """Test: Evidence index links bid items to quantity_evidence from cost items."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        project_id = "test_project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Create bid_proposal.json
        bid_proposal = {
            "project_id": project_id,
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [
                {
                    "division": "03 Concrete",
                    "description": "Concrete Slab",
                    "quantity": 100.0,
                    "unit": "SF",
                    "unit_cost": 10.0,
                    "total_cost": 1000.0,
                    "basis": "From drawing",
                    "confidence": 0.9,
                    "quantity_source": "from_drawing",
                }
            ],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
        }
        with open(project_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_proposal, f)

        # Create costing_result.json with quantity_evidence
        costing_result = {
            "project_id": project_id,
            "breakdown_by_category": [
                {
                    "category": "Concrete",
                    "items": [
                        {
                            "item_name": "Concrete Slab",
                            "quantity": 100.0,
                            "unit": "SF",
                            "unit_cost": 10.0,
                            "subtotal": 1000.0,
                            "quantity_source": "from_drawing",
                            "quantity_confidence": 0.9,
                            "quantity_evidence": {
                                "page_number": 5,
                                "sheet_id": "S-1",
                                "evidence_snippet": "Slab on grade, 100 SF",
                                "location_type": "schedule",
                            },
                        }
                    ],
                    "subtotal": 1000.0,
                }
            ],
            "total_cost": 1000.0,
        }
        with open(project_dir / "costing_result.json", "w") as f:
            json.dump(costing_result, f)

        # Create extraction_result.json
        extraction_result = {
            "project_type": "institutional",
            "scope_type": "new_construction",
            "scope_of_work": [],
        }
        with open(project_dir / "extraction_result.json", "w") as f:
            json.dump(extraction_result, f)

        # Create model_3d.json
        model_3d = {
            "buildings": [],
            "work_zones": [
                {
                    "zone_name": "Gymnasium",
                    "zone_type": "room",
                    "page_number": 3,
                    "evidence": "Gymnasium shown on plan",
                }
            ],
            "geometry": {"units": "feet", "coordinate_system": "right_handed_y_up"},
            "materials": {},
        }
        with open(project_dir / "model_3d.json", "w") as f:
            json.dump(model_3d, f)

        # Generate index
        index = generate_evidence_index(project_id, output_dir)

        # Verify bid item evidence
        assert len(index.bid_item_evidence) == 1
        bid_evidence = index.bid_item_evidence[0]
        assert bid_evidence.line_item_index == 0
        assert bid_evidence.description == "Concrete Slab"
        assert len(bid_evidence.evidence_references) == 1
        assert bid_evidence.evidence_references[0].page_number == 5
        assert bid_evidence.evidence_references[0].sheet_id == "S-1"
        assert "Slab" in bid_evidence.evidence_references[0].evidence_snippet

        # Verify zone evidence
        assert len(index.zone_evidence) == 1
        zone_evidence = index.zone_evidence[0]
        assert zone_evidence.zone_id == "Gymnasium"
        assert zone_evidence.zone_type == "room"
        assert len(zone_evidence.evidence_references) == 1
        assert zone_evidence.evidence_references[0].page_number == 3


def test_generate_evidence_index_handles_missing_evidence() -> None:
    """Test: Index handles missing evidence gracefully."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        project_id = "test_project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Create minimal artifacts
        bid_proposal = {
            "project_id": project_id,
            "summary": {"total_cost": 0.0, "cost_by_division": {}},
            "line_items": [
                {
                    "division": "01 General",
                    "description": "Allowance Item",
                    "quantity": None,
                    "unit": None,
                    "unit_cost": None,
                    "total_cost": 5000.0,
                    "basis": "Allowance",
                    "confidence": 0.5,
                }
            ],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
        }
        with open(project_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_proposal, f)

        costing_result = {
            "project_id": project_id,
            "breakdown_by_category": [],
            "total_cost": 5000.0,
        }
        with open(project_dir / "costing_result.json", "w") as f:
            json.dump(costing_result, f)

        extraction_result = {
            "project_type": "institutional",
            "scope_type": "new_construction",
            "scope_of_work": [],
        }
        with open(project_dir / "extraction_result.json", "w") as f:
            json.dump(extraction_result, f)

        model_3d = {
            "buildings": [],
            "work_zones": [],
            "geometry": {"units": "feet", "coordinate_system": "right_handed_y_up"},
            "materials": {},
        }
        with open(project_dir / "model_3d.json", "w") as f:
            json.dump(model_3d, f)

        # Generate index (should not raise)
        index = generate_evidence_index(project_id, output_dir)

        # Verify bid item has no evidence references
        assert len(index.bid_item_evidence) == 1
        assert len(index.bid_item_evidence[0].evidence_references) == 0


def test_save_evidence_index() -> None:
    """Test: Evidence index is saved to JSON file."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        project_id = "test_project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Create minimal artifacts
        for filename in ["bid_proposal.json", "costing_result.json", "extraction_result.json", "model_3d.json"]:
            with open(project_dir / filename, "w") as f:
                json.dump({"project_id": project_id}, f)

        index = generate_evidence_index(project_id, output_dir)
        output_path = save_evidence_index(project_id, index, output_dir)

        assert output_path.exists()
        assert output_path.name == "evidence_index.json"

        # Verify JSON is valid
        with open(output_path, "r") as f:
            data = json.load(f)
            assert data["project_id"] == project_id
            assert "bid_item_evidence" in data
            assert "zone_evidence" in data


def test_generate_evidence_index_raises_on_missing_artifacts() -> None:
    """Test: Index generation raises FileNotFoundError if required artifacts missing."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        project_id = "test_project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Missing bid_proposal.json
        with pytest.raises(FileNotFoundError):
            generate_evidence_index(project_id, output_dir)






