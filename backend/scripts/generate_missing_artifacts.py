"""Script to manually generate missing artifacts for an existing project.

This is useful when artifacts failed to generate during pipeline run or need to be regenerated.
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.services.trade_assembly_generator import generate_trade_assemblies
from app.services.general_conditions_estimator import estimate_general_conditions
from app.services.labor_synthesizer import generate_labor_breakdown
from app.services.proposal_sections_generator import generate_proposal_sections
from app.schemas.bid_proposal import BidProposal
from app.schemas.evidence_index import EvidenceIndex
from app.schemas.model_3d import Model3D
from app.schemas.trade_assemblies import TradeAssembliesResult
from loguru import logger


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_missing_artifacts.py <project_id>")
        sys.exit(1)
    
    project_id = sys.argv[1]
    output_dir = Path("out") / project_id
    
    if not output_dir.exists():
        print(f"Error: Project directory not found: {output_dir}")
        sys.exit(1)
    
    settings = get_settings()
    logger.info(f"Generating missing artifacts for project: {project_id}")
    
    # Load required artifacts
    try:
        with open(output_dir / "bid_proposal.json") as f:
            bid_proposal = BidProposal.model_validate(json.load(f))
        logger.info("✅ Loaded bid_proposal.json")
    except Exception as e:
        logger.error(f"Failed to load bid_proposal.json: {e}")
        sys.exit(1)
    
    # Load evidence_index (create if missing)
    evidence_index = None
    evidence_index_file = output_dir / "evidence_index.json"
    if evidence_index_file.exists():
        try:
            with open(evidence_index_file) as f:
                evidence_index = EvidenceIndex.model_validate(json.load(f))
            logger.info("✅ Loaded evidence_index.json")
        except Exception as e:
            logger.warning(f"Failed to load evidence_index.json: {e}")
    else:
        logger.warning("evidence_index.json not found - trade assemblies may fail")
    
    # Load model_3d
    model_3d = None
    model_3d_file = output_dir / "model_3d.json"
    if model_3d_file.exists():
        try:
            with open(model_3d_file) as f:
                model_3d = Model3D.model_validate(json.load(f))
            logger.info("✅ Loaded model_3d.json")
        except Exception as e:
            logger.warning(f"Failed to load model_3d.json: {e}")
    
    # Load document_analysis
    document_analysis = None
    doc_analysis_file = output_dir / "document_analysis.json"
    if doc_analysis_file.exists():
        try:
            with open(doc_analysis_file) as f:
                from app.schemas.document_analysis import DocumentAnalysis
                document_analysis = DocumentAnalysis.model_validate(json.load(f))
            logger.info("✅ Loaded document_analysis.json")
        except Exception as e:
            logger.warning(f"Failed to load document_analysis.json: {e}")
    
    # 1. Generate Trade Assemblies
    if not (output_dir / "trade_assemblies.json").exists():
        logger.info("Generating trade_assemblies.json...")
        try:
            trade_assemblies = generate_trade_assemblies(
                project_id=project_id,
                bid_proposal=bid_proposal,
                evidence_index=evidence_index,
                ruleset="row_house_repair.yml",
                settings=settings,
            )
            with open(output_dir / "trade_assemblies.json", "w") as f:
                f.write(trade_assemblies.model_dump_json(indent=2))
            logger.info(f"✅ Generated trade_assemblies.json ({len(trade_assemblies.assemblies)} assemblies)")
        except Exception as e:
            logger.error(f"❌ Failed to generate trade_assemblies: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.info("✅ trade_assemblies.json already exists")
    
    # 2. Generate General Conditions
    if not (output_dir / "general_conditions.json").exists():
        logger.info("Generating general_conditions.json...")
        try:
            # Determine building type
            building_type = "row_house"
            if document_analysis:
                building_type = document_analysis.resolved_project_type or document_analysis.project_type
            
            # Get region resolution
            region_resolution = None
            try:
                expanded_scope_file = output_dir / "expanded_scope.json"
                if expanded_scope_file.exists():
                    with open(expanded_scope_file) as f:
                        expanded_scope_data = json.load(f)
                    region_resolution = expanded_scope_data.get("region_resolution")
            except Exception:
                pass
            
            # Resolve region if needed
            if region_resolution is None:
                from app.services.region_resolver import resolve_region
                document_analysis_dict = document_analysis.model_dump() if document_analysis else None
                extraction_result_dict = None
                extraction_file = output_dir / "extraction_result.json"
                if extraction_file.exists():
                    with open(extraction_file) as f:
                        extraction_result_dict = json.load(f)
                region_resolution = resolve_region(document_analysis_dict, extraction_result_dict)
            
            general_conditions = estimate_general_conditions(
                project_id=project_id,
                building_type=building_type,
                bid_proposal=bid_proposal,
                model_3d=model_3d,
                document_analysis=document_analysis.model_dump() if document_analysis else None,
                extraction_result=None,
                region_resolution=region_resolution,
                settings=settings,
            )
            with open(output_dir / "general_conditions.json", "w") as f:
                f.write(general_conditions.model_dump_json(indent=2))
            logger.info(f"✅ Generated general_conditions.json ({len(general_conditions.items)} items, ${general_conditions.total_cost:,.2f} total)")
        except Exception as e:
            logger.error(f"❌ Failed to generate general_conditions: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.info("✅ general_conditions.json already exists")
    
    # 3. Generate Labor Breakdown
    if not (output_dir / "labor_breakdown.json").exists():
        logger.info("Generating labor_breakdown.json...")
        try:
            # Load trade assemblies if available
            trade_assemblies_obj = None
            assemblies_file = output_dir / "trade_assemblies.json"
            if assemblies_file.exists():
                try:
                    with open(assemblies_file) as f:
                        trade_assemblies_obj = TradeAssembliesResult.model_validate(json.load(f))
                except Exception:
                    pass
            
            # Get profile_id
            profile_id = None
            try:
                expanded_scope_file = output_dir / "expanded_scope.json"
                if expanded_scope_file.exists():
                    with open(expanded_scope_file) as f:
                        expanded_scope_data = json.load(f)
                    profile_id = expanded_scope_data.get("profile_id")
            except Exception:
                pass
            
            # Get region_resolution
            region_resolution = None
            try:
                expanded_scope_file = output_dir / "expanded_scope.json"
                if expanded_scope_file.exists():
                    with open(expanded_scope_file) as f:
                        expanded_scope_data = json.load(f)
                    region_resolution = expanded_scope_data.get("region_resolution")
            except Exception:
                pass
            
            labor_breakdown = generate_labor_breakdown(
                project_id=project_id,
                output_dir=output_dir,
                settings=settings,
                profile_id=profile_id,
                region_resolution=region_resolution,
                trade_assemblies=trade_assemblies_obj,
            )
            # Note: generate_labor_breakdown saves it automatically, but let's verify
            if (output_dir / "labor_breakdown.json").exists():
                logger.info(f"✅ Generated labor_breakdown.json ({len(labor_breakdown.activities)} activities)")
            else:
                # Save it manually
                with open(output_dir / "labor_breakdown.json", "w") as f:
                    f.write(labor_breakdown.model_dump_json(indent=2))
                logger.info(f"✅ Generated labor_breakdown.json ({len(labor_breakdown.activities)} activities)")
        except Exception as e:
            logger.error(f"❌ Failed to generate labor_breakdown: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.info("✅ labor_breakdown.json already exists")
    
    logger.info("✅ Done!")


if __name__ == "__main__":
    main()





