"use client";

import { useState, useEffect } from "react";
import { ProjectSummary, api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckCircle2, XCircle, AlertTriangle, Shield } from "lucide-react";
import { getTerm } from "@/lib/terminology";

interface OverviewTabProps {
  projectId: string;
  summary: ProjectSummary;
  contractorMode?: boolean; // Phase 10.13A
}

interface BidReadinessV2 {
  conceptual_ready: boolean;
  contractor_ready: boolean;
  blocking_reasons_contractor: string[];
  warnings_contractor: string[];
  derived_from: Record<string, any>;
}

interface CaseStudy {
  project_id: string;
  baseline_cost: number;
  adjusted_cost: number;
  compliance_adjustments: string[];
  narrative: string;
}

interface DocumentAnalysis {
  procurement_context?: {
    is_public_project: boolean;
    issuing_authority?: string | null;
    indicators?: string[];
  } | null;
  requires_prevailing_wage?: boolean | null;
  requires_bonds?: boolean | null;
}

export function OverviewTab({ projectId, summary, contractorMode = false }: OverviewTabProps) {
  const [readinessV2, setReadinessV2] = useState<BidReadinessV2 | null>(null);
  const [caseStudy, setCaseStudy] = useState<CaseStudy | null>(null);
  const [documentAnalysis, setDocumentAnalysis] = useState<DocumentAnalysis | null>(null);

  useEffect(() => {
    const loadReadinessV2 = async () => {
      try {
        const data = await api.getBidReadinessV2(projectId);
        setReadinessV2(data);
      } catch (err) {
        // Readiness v2 might not be available
        console.warn("[OverviewTab] Failed to load bid readiness v2:", err);
      }
    };

    // Phase 1: Load case study
    const loadCaseStudy = async () => {
      try {
        const data = await api.getArtifact<CaseStudy>(projectId, "case_study");
        setCaseStudy(data);
      } catch (err) {
        // Case study might not be available
        console.warn("[OverviewTab] Failed to load case study:", err);
      }
    };

    // Phase 1: Load document analysis for compliance flags
    const loadDocumentAnalysis = async () => {
      try {
        const data = await api.getArtifact<DocumentAnalysis>(projectId, "document_analysis");
        setDocumentAnalysis(data);
      } catch (err) {
        // Document analysis might not be available
        console.warn("[OverviewTab] Failed to load document analysis:", err);
      }
    };

    loadReadinessV2();
    loadCaseStudy();
    loadDocumentAnalysis();
  }, [projectId]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Badge variant={summary.status === "succeeded" ? "default" : "secondary"}>
                {summary.status}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {summary.validation_score !== undefined && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Validation Score</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold">
                  {(summary.validation_score * 100).toFixed(0)}%
                </span>
                {summary.validation_passed ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500" />
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {summary.total_cost !== undefined && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">
                ${summary.total_cost.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </CardContent>
          </Card>
        )}

        {summary.bid_ready !== undefined && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Bid Ready</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {/* Conceptual Readiness */}
                <div className="flex items-center gap-2">
                  {summary.bid_ready ? (
                    <>
                      <CheckCircle2 className="h-5 w-5 text-green-500" />
                      <span className="font-medium">Conceptual Ready</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="h-5 w-5 text-yellow-500" />
                      <span className="font-medium">Conceptual Not Ready</span>
                    </>
                  )}
                </div>
                
                {/* Contractor Readiness (Phase 10.1) */}
                {readinessV2 && (
                  <div className="flex items-center gap-2 pt-2 border-t">
                    {readinessV2.contractor_ready ? (
                      <>
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                        <span className="font-medium">Contractor Ready</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="h-5 w-5 text-yellow-500" />
                        <span className="font-medium">Contractor Not Ready</span>
                      </>
                    )}
                  </div>
                )}
                
                {summary.estimate_mode && (
                  <p className="text-sm text-gray-500 mt-1">
                    Mode: {summary.estimate_mode}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {summary.geometry_quality && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Geometry Quality</CardTitle>
            </CardHeader>
            <CardContent>
              <Badge variant={
                summary.geometry_quality === "authoritative" ? "default" :
                summary.geometry_quality === "derived_from_area" ? "secondary" :
                "outline"
              }>
                {getTerm(summary.geometry_quality)}
              </Badge>
            </CardContent>
          </Card>
        )}
      </div>

      {summary.bid_ready === false && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            This bid is not ready for submission. Some quantities are estimated or unknown.
            Please review the Bid tab for details.
          </AlertDescription>
        </Alert>
      )}

      {summary.validation_passed === false && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertDescription>
            Validation failed. Please review the Evidence tab for validation issues.
          </AlertDescription>
        </Alert>
      )}

      {/* Phase 1: Compliance Flags Panel */}
      {documentAnalysis && (
        (documentAnalysis.procurement_context?.is_public_project ||
          documentAnalysis.requires_prevailing_wage ||
          documentAnalysis.requires_bonds) && (
          <Card className="border-blue-200 bg-blue-50/50">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-blue-600" />
                <CardTitle className="text-lg">Compliance & Procurement</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {documentAnalysis.procurement_context?.is_public_project && (
                <div className="flex items-center gap-2">
                  <Badge variant="default">Government/Public Project</Badge>
                  {documentAnalysis.procurement_context.issuing_authority && (
                    <span className="text-sm text-muted-foreground">
                      ({documentAnalysis.procurement_context.issuing_authority})
                    </span>
                  )}
                </div>
              )}
              {documentAnalysis.requires_prevailing_wage && (
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Prevailing Wage Required</Badge>
                  <span className="text-sm text-muted-foreground">
                    Labor rates adjusted for Davis-Bacon or state prevailing wage laws
                  </span>
                </div>
              )}
              {documentAnalysis.requires_bonds && (
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Bonds Required</Badge>
                  <span className="text-sm text-muted-foreground">
                    Performance and payment bonds included in bid
                  </span>
                </div>
              )}
              {documentAnalysis.procurement_context?.indicators && 
                documentAnalysis.procurement_context.indicators.length > 0 && (
                <div className="text-xs text-muted-foreground pt-2 border-t">
                  <div className="font-medium mb-1">Detection Indicators:</div>
                  <div className="flex flex-wrap gap-1">
                    {documentAnalysis.procurement_context.indicators.map((ind, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs">
                        {ind}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )
      )}

      {/* Phase 1: Case Study Panel */}
      {caseStudy && (
        <Card className="border-purple-200 bg-purple-50/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-purple-600" />
                <CardTitle className="text-lg">Compliance Case Study</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {caseStudy.baseline_cost !== undefined && caseStudy.adjusted_cost !== undefined && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Baseline Cost</div>
                  <div className="text-lg font-bold">
                    ${caseStudy.baseline_cost.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Adjusted Cost</div>
                  <div className="text-lg font-bold text-purple-600">
                    ${caseStudy.adjusted_cost.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                </div>
              </div>
            )}
            {caseStudy.compliance_adjustments && caseStudy.compliance_adjustments.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">Applied Adjustments:</div>
                <ul className="text-sm space-y-1 list-disc list-inside text-muted-foreground">
                  {caseStudy.compliance_adjustments.map((adj, idx) => (
                    <li key={idx}>{adj}</li>
                  ))}
                </ul>
              </div>
            )}
            {caseStudy.narrative && (
              <div className="pt-2 border-t">
                <div className="text-sm font-medium mb-1">Narrative:</div>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{caseStudy.narrative}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Trust & Disclosure Panel (Phase 9.4) */}
      <Card className="border-emerald-200 bg-emerald-50/50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-emerald-600" />
            <CardTitle className="text-lg">Trust & Scope</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {summary.validation_score !== undefined && (
            <div>
              <div className="text-sm font-medium mb-1">Bid Confidence Score</div>
              <div className="text-2xl font-bold text-emerald-600">
                {(summary.validation_score * 100).toFixed(0)}%
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Based on validation checks and evidence coverage
              </p>
            </div>
          )}
          
          <div className="space-y-3 pt-2 border-t">
            <div>
              <div className="text-sm font-medium mb-1">What this bid includes:</div>
              <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
                <li>Line items with quantities and unit costs</li>
                <li>Drawing references for each item</li>
                <li>3D geometry visualization</li>
                <li>Cost breakdown by division</li>
              </ul>
            </div>
            
            <div>
              <div className="text-sm font-medium mb-1">What this bid does NOT include:</div>
              <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
                <li>Field verification or site visits</li>
                <li>Permits or regulatory approvals</li>
                <li>Contingencies or markups</li>
                <li>Final engineering review</li>
              </ul>
            </div>
            
            <Alert className="bg-white border-emerald-200">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertDescription className="text-xs">
                <strong>Disclaimer:</strong> This bid is evidence-backed but does not replace field verification.
                All quantities and costs should be reviewed by a qualified professional before submission.
              </AlertDescription>
            </Alert>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

