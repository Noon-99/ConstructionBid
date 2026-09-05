#!/usr/bin/env python3
"""Verification script to ensure compliance detection works end-to-end."""

import json
import sys
from pathlib import Path

def verify_project(project_id: str) -> bool:
    """Verify that compliance detection worked for a project."""
    project_root = Path(__file__).parent.parent.parent
    output_dir = project_root / "out" / project_id
    
    if not output_dir.exists():
        print(f"❌ Project output directory not found: {output_dir}")
        return False
    
    # Check document_analysis.json
    doc_analysis_file = output_dir / "document_analysis.json"
    if not doc_analysis_file.exists():
        print(f"❌ document_analysis.json not found")
        return False
    
    with open(doc_analysis_file) as f:
        doc_analysis = json.load(f)
    
    print(f"\n{'='*60}")
    print(f"Verifying Compliance Detection for Project: {project_id}")
    print(f"{'='*60}\n")
    
    # Check procurement context
    procurement_context = doc_analysis.get("procurement_context")
    if procurement_context:
        is_public = procurement_context.get("is_public_project", False)
        confidence = procurement_context.get("detection_confidence", 0.0)
        issuing_authority = procurement_context.get("issuing_authority")
        indicators = procurement_context.get("indicators", [])
        
        print(f"📋 Procurement Context:")
        print(f"   ✓ is_public_project: {is_public}")
        print(f"   ✓ detection_confidence: {confidence:.2f}")
        print(f"   ✓ issuing_authority: {issuing_authority or 'None'}")
        print(f"   ✓ indicators: {len(indicators)} found")
        if indicators:
            for ind in indicators[:5]:  # Show first 5
                print(f"      - {ind}")
    else:
        print(f"❌ procurement_context missing from document_analysis.json")
        return False
    
    # Check compliance flags
    requires_prevailing_wage = doc_analysis.get("requires_prevailing_wage")
    requires_bonds = doc_analysis.get("requires_bonds")
    
    print(f"\n📋 Compliance Flags:")
    print(f"   ✓ requires_prevailing_wage: {requires_prevailing_wage}")
    print(f"   ✓ requires_bonds: {requires_bonds}")
    
    # Check costing result
    costing_file = output_dir / "costing_result.json"
    if costing_file.exists():
        with open(costing_file) as f:
            costing = json.load(f)
        
        compliance_costs = costing.get("compliance_costs", {})
        compliance_total = costing.get("compliance_total", 0.0)
        base_scope_cost = costing.get("base_scope_cost", 0.0)
        total_cost = costing.get("total_cost", 0.0)
        compliance_adjustments = costing.get("compliance_adjustments", [])
        
        print(f"\n💰 Costing Results:")
        print(f"   ✓ base_scope_cost: ${base_scope_cost:,.2f}")
        print(f"   ✓ compliance_costs: {compliance_costs}")
        print(f"   ✓ compliance_total: ${compliance_total:,.2f}")
        print(f"   ✓ total_cost: ${total_cost:,.2f}")
        print(f"   ✓ compliance_adjustments: {len(compliance_adjustments)} found")
        if compliance_adjustments:
            for adj in compliance_adjustments[:3]:  # Show first 3
                print(f"      - {adj[:80]}...")
    else:
        print(f"\n⚠️  costing_result.json not found (may still be processing)")
    
    # Check bid proposal
    bid_proposal_file = output_dir / "bid_proposal.json"
    if bid_proposal_file.exists():
        with open(bid_proposal_file) as f:
            bid_proposal = json.load(f)
        
        line_items = bid_proposal.get("line_items", [])
        compliance_line_items = [
            li for li in line_items 
            if any(keyword in li.get("description", "").lower() 
                   for keyword in ["bond", "insurance", "contingency"])
        ]
        
        print(f"\n📄 Bid Proposal:")
        print(f"   ✓ total line items: {len(line_items)}")
        print(f"   ✓ compliance line items: {len(compliance_line_items)}")
        if compliance_line_items:
            for li in compliance_line_items:
                print(f"      - {li.get('description')}: ${li.get('total_cost', 0):,.2f}")
        else:
            print(f"   ⚠️  No compliance line items found in bid proposal")
    
    # Summary
    print(f"\n{'='*60}")
    if procurement_context and procurement_context.get("is_public_project"):
        print(f"✅ Government project detected successfully!")
        if requires_prevailing_wage or requires_bonds:
            print(f"✅ Compliance flags set correctly!")
        else:
            print(f"⚠️  Compliance flags not set (may be intentional)")
        return True
    else:
        print(f"⚠️  Government project not detected (may not be a government project)")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_compliance_detection.py <project_id>")
        sys.exit(1)
    
    project_id = sys.argv[1]
    success = verify_project(project_id)
    sys.exit(0 if success else 1)
