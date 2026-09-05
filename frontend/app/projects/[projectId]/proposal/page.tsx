"use client";

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api, ApiError, type BidReadiness } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Printer, Download, FileJson, AlertCircle, CheckCircle2, AlertTriangle, RotateCcw, ExternalLink, FileText } from "lucide-react";
import { getTerm } from "@/lib/terminology";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import type { EvidenceRef } from "@/lib/evidence-normalizer";

interface BidProposal {
  project_id: string;
  summary: {
    total_cost: number;
    cost_by_division: Record<string, number>;
  };
  line_items: Array<{
    division: string;
    description: string;
    quantity: number | null;
    unit: string | null;
    unit_cost: number | null;
    total_cost: number;
    basis: string;
    confidence: number;
    quantity_source?: string | null;
    quantity_confidence?: number | null;
  }>;
  allowances: Array<{
    name: string;
    amount: number;
    notes: string;
  }>;
  clarifications: Array<{
    text: string;
    severity: "info" | "warning" | "critical";
  }>;
  generated_at: string;
  estimate_mode: "conceptual" | "bid_ready";
  bid_ready: boolean;
}

interface ValidationReport {
  passed: boolean;
  score: number;
  issues: Array<{
    code: string;
    severity: string;
    message: string;
  }>;
}

interface DocumentAnalysis {
  project_name?: string;
  project_address?: string;
  project_location?: string;
}

interface EvidenceReference {
  page_number: number;
  sheet_id?: string | null;
  evidence_snippet?: string; // Backend uses evidence_snippet
  snippet?: string; // Also accept snippet for compatibility
  location_type?: string | null;
  bbox?: { x0: number; y0: number; x1: number; y1: number } | null;
  bbox_source?: "none" | "vision_box" | "heuristic" | null;
}

interface BidReview {
  line_items?: Array<{
    line_item_index: number;
    evidence_refs?: EvidenceReference[];
  }>;
}

// Phase 10.9A: Proposal Sections interfaces
interface ProposalSections {
  project_id: string;
  generated_at: string;
  executive_summary: {
    project_overview: string;
    total_bid_amount: number;
    scope_summary: string;
    key_highlights: string[];
  };
  scope_sections: Array<{
    section_key: string;
    title: string;
    narrative: string;
    line_item_ids: string[];
    evidence_refs: EvidenceReference[];
    detail_refs: string[];
    flags: string[];
  }>;
  logistics_section: {
    title: string;
    narrative: string;
    line_item_ids: string[];
    evidence_refs: EvidenceReference[];
  };
  permits_inspections_section: {
    title: string;
    narrative: string;
    line_item_ids: string[];
    evidence_refs: EvidenceReference[];
  };
  exclusions: string[];
  assumptions: string[];
  payment_schedule: {
    milestone_1?: string | null;
    milestone_2?: string | null;
    milestone_3?: string | null;
    final_payment?: string | null;
  };
  schedule: {
    estimated_duration_weeks?: number | null;
    start_conditions: string[];
    critical_path_items: string[];
  };
  notes: string[];
}

export default function ProposalPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const projectId = params.projectId as string;
  const isPrintMode = searchParams.get("print") === "1";
  const showHighlights = searchParams.get("highlights") === "1" && isPrintMode;

  const [bidProposal, setBidProposal] = useState<BidProposal | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [documentAnalysis, setDocumentAnalysis] = useState<DocumentAnalysis | null>(null);
  const [bidReadiness, setBidReadiness] = useState<BidReadiness | null>(null);
  const [bidReview, setBidReview] = useState<BidReview | null>(null);
  const [proposalSections, setProposalSections] = useState<ProposalSections | null>(null);
  const [pricingProfile, setPricingProfile] = useState<any | null>(null); // Phase 10.13A
  const [proposalPdfStatus, setProposalPdfStatus] = useState<"idle" | "generating" | "ready" | "error">("idle"); // Phase 10.13A
  const [coverageDeclarations, setCoverageDeclarations] = useState<any | null>(null); // Coverage & Warranty declarations
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRef[]>([]);
  const [selectedEvidenceTitle, setSelectedEvidenceTitle] = useState("");

  useEffect(() => {
    const loadData = async () => {
      try {
        // Load bid proposal (required)
        const bidData = await api.getArtifact<BidProposal>(projectId, "bid_proposal");
        setBidProposal(bidData);

        // Load validation report (optional)
        try {
          const validationData = await api.getArtifact<ValidationReport>(
            projectId,
            "validation_report"
          );
          setValidationReport(validationData);
        } catch (e) {
          // Validation report might not exist
        }

        // Load document analysis for project name/address (optional)
        try {
          const analysisData = await api.getArtifact<DocumentAnalysis>(
            projectId,
            "document_analysis"
          );
          setDocumentAnalysis(analysisData);
        } catch (e) {
          // Document analysis might not exist
        }

        // Load bid readiness (Phase 6.5)
        try {
          const readinessData = await api.getBidReadiness(projectId);
          setBidReadiness(readinessData);
        } catch (e) {
          // Bid readiness might not be available
        }

        // Load bid_review for evidence highlights (Phase 10.4)
        if (showHighlights) {
          try {
            const reviewData = await api.getArtifact<BidReview>(projectId, "bid_review");
            setBidReview(reviewData);
          } catch (e) {
            // Bid review might not exist
          }
        }

        // Load proposal_sections (Phase 10.9A)
        try {
          const sectionsData = await api.getArtifact<ProposalSections>(projectId, "proposal_sections");
          setProposalSections(sectionsData);
        } catch (e) {
          // Proposal sections might not exist, fallback to legacy rendering
        }

        // Load coverage_declarations (Coverage & Warranty)
        try {
          const coverageData = await api.getArtifact<any>(projectId, "coverage_declarations");
          setCoverageDeclarations(coverageData);
        } catch (e) {
          // Coverage declarations might not exist
          setCoverageDeclarations(null);
        }

        setError(null);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load proposal data.");
        }
        console.error("Load error:", err);
      } finally {
        setLoading(false);
        // Mark proposal as ready for PDF generation
        if (typeof document !== "undefined") {
          const marker = document.getElementById("proposal-ready");
          if (marker) {
            marker.setAttribute("data-ready", "true");
          }
        }
      }
    };

    loadData();
  }, [projectId, showHighlights]);

  const handlePrint = () => {
    window.print();
  };

  const handleDownloadJson = async (artifactName: string) => {
    try {
      const data = await api.getArtifact(projectId, artifactName);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${artifactName}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download error:", err);
      alert("Failed to download JSON file.");
    }
  };

  const getQuantitySourceBadge = (source: string | null | undefined) => {
    if (!source) return null;
    return (
      <Badge variant="outline" className="ml-2 text-xs">
        {getTerm(source)}
      </Badge>
    );
  };

  // Convert EvidenceReference to EvidenceRef for EvidenceDrawer
  const convertEvidenceRef = (ref: EvidenceReference): EvidenceRef => {
    const evidenceRef: EvidenceRef = {
      page_number: ref.page_number,
    };
    // Backend uses evidence_snippet, but also accept snippet for compatibility
    evidenceRef.snippet = ref.evidence_snippet || ref.snippet || null;
    if (ref.bbox) evidenceRef.bbox = ref.bbox;
    if (ref.bbox_source) evidenceRef.bbox_source = ref.bbox_source;
    if (ref.sheet_id !== undefined) evidenceRef.sheet_id = ref.sheet_id;
    if (ref.location_type !== undefined) evidenceRef.location_type = ref.location_type;
    return evidenceRef;
  };

  const handleEvidenceClick = (evidenceRefs: EvidenceReference[], title: string) => {
    setSelectedEvidence(evidenceRefs.map(convertEvidenceRef));
    setSelectedEvidenceTitle(title);
    setEvidenceDrawerOpen(true);
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  if (error || !bidProposal) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error || "Bid proposal not found. Please ensure the project has been processed."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const projectName = documentAnalysis?.project_name || "Project Name Not Available";
  const projectAddress =
    documentAnalysis?.project_address ||
    documentAnalysis?.project_location ||
    "Address not available";
  const generatedDate = new Date(bidProposal.generated_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  // Group line items by division
  const itemsByDivision: Record<string, typeof bidProposal.line_items> = {};
  bidProposal.line_items.forEach((item) => {
    if (!itemsByDivision[item.division]) {
      itemsByDivision[item.division] = [];
    }
    itemsByDivision[item.division].push(item);
  });

  // Collect evidence with bbox for highlights (Phase 10.4)
  const evidenceByPage: Record<number, EvidenceReference[]> = {};
  if (showHighlights && bidReview && bidReview.line_items) {
    for (const item of bidReview.line_items) {
      if (item.evidence_refs) {
        for (const ref of item.evidence_refs) {
          if (ref.bbox && ref.page_number > 0) {
            if (!evidenceByPage[ref.page_number]) {
              evidenceByPage[ref.page_number] = [];
            }
            evidenceByPage[ref.page_number].push(ref);
          }
        }
      }
    }
  }

  const renderPageWithHighlights = (pageNumber: number) => {
    if (!showHighlights || !evidenceByPage[pageNumber] || evidenceByPage[pageNumber].length === 0) {
      return null;
    }

    const pageUrl = api.getPageImageUrl(projectId, pageNumber);
    const pageEvidence = evidenceByPage[pageNumber];

    return (
      <div key={pageNumber} className="mb-8 print-page-break print-avoid-break">
        <h3 className="text-lg font-semibold mb-2">Page {pageNumber} - Evidence Highlights</h3>
        <div className="relative inline-block max-w-full">
          <img
            src={pageUrl}
            alt={`Page ${pageNumber}`}
            className="max-w-full h-auto shadow-lg"
          />
          {pageEvidence.map((ref, idx) => {
            if (!ref.bbox) return null;
            const { x0, y0, x1, y1 } = ref.bbox;
            return (
              <div
                key={idx}
                className="absolute border-2 border-blue-500 bg-blue-500/20 pointer-events-none"
                style={{
                  left: `${x0 * 100}%`,
                  top: `${y0 * 100}%`,
                  width: `${(x1 - x0) * 100}%`,
                  height: `${(y1 - y0) * 100}%`,
                }}
              />
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Phase 10.13A: Improved Print Styles */}
      <style jsx global>{`
        @media print {
          .no-print {
            display: none !important;
          }
          .print-only {
            display: block !important;
          }
          .print-page-break {
            page-break-before: always;
          }
          .print-avoid-break {
            page-break-inside: avoid;
          }
          body {
            margin: 0;
            padding: 0;
            background: white;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
          }
          .container {
            max-width: 100% !important;
            padding: 0 !important;
          }
          /* Phase 10.13A: Consistent margins */
          @page {
            margin: 0.75in;
            size: letter;
          }
          /* Phase 10.13A: Print header */
          .print-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 0.5in;
            padding: 0.15in 0.75in;
            background: white;
            border-bottom: 1px solid #ddd;
            font-size: 10pt;
            color: #666;
            text-align: center;
          }
          /* Phase 10.13A: Print footer */
          .print-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 0.5in;
            padding: 0.15in 0.75in;
            background: white;
            border-top: 1px solid #ddd;
            font-size: 9pt;
            color: #666;
            text-align: center;
          }
          /* Phase 10.13A: Improved typography */
          h1 {
            font-size: 28pt !important;
            font-weight: 700 !important;
            margin-bottom: 0.5em !important;
            color: #1a1a1a !important;
            line-height: 1.2 !important;
          }
          h2 {
            font-size: 20pt !important;
            font-weight: 600 !important;
            margin-top: 1em !important;
            margin-bottom: 0.5em !important;
            color: #2a2a2a !important;
            line-height: 1.3 !important;
          }
          h3 {
            font-size: 16pt !important;
            font-weight: 600 !important;
            margin-top: 0.75em !important;
            margin-bottom: 0.4em !important;
            color: #3a3a3a !important;
          }
          h4 {
            font-size: 14pt !important;
            font-weight: 600 !important;
            margin-top: 0.5em !important;
            margin-bottom: 0.3em !important;
          }
          p {
            line-height: 1.6 !important;
            margin-bottom: 0.5em !important;
          }
          /* Better spacing for sections */
          .proposal-section {
            margin-bottom: 1.5em !important;
          }
        }
        .print-only {
          display: none;
        }
        /* Phase 10.13A: Better spacing in screen mode */
        h1 {
          font-size: 2.5rem;
          font-weight: 700;
          margin-bottom: 1rem;
          line-height: 1.2;
        }
        h2 {
          font-size: 1.875rem;
          font-weight: 600;
          margin-top: 2rem;
          margin-bottom: 1rem;
          line-height: 1.3;
        }
        h3 {
          font-size: 1.5rem;
          font-weight: 600;
          margin-top: 1.5rem;
          margin-bottom: 0.75rem;
        }
      `}</style>

      {/* Proposal-ready marker for Playwright */}
      <div id="proposal-ready" data-ready="false" style={{ display: "none" }} />

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        {/* Bid Readiness Stamp (Phase 6.5) */}
        {bidReadiness && (
          <div className={`mb-6 p-4 rounded-lg border-2 print-avoid-break ${
            bidReadiness.bid_ready
              ? "bg-green-50 border-green-500 text-green-900"
              : "bg-amber-50 border-amber-500 text-amber-900"
          }`}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-2xl font-bold">
                {bidReadiness.readiness_stamp_text}
              </h2>
              <Badge variant={bidReadiness.bid_ready ? "default" : "secondary"}>
                Score: {(bidReadiness.readiness_score * 100).toFixed(0)}%
              </Badge>
            </div>
            
            {validationReport && (
              <div className="text-sm mb-2">
                <span className="font-medium">Validation: </span>
                <Badge variant={validationReport.passed ? "default" : "destructive"}>
                  {validationReport.passed ? "Passed" : "Failed"} ({(validationReport.score * 100).toFixed(0)}%)
                </Badge>
              </div>
            )}

            {bidReadiness.derived_from.geometry_quality && (
              <div className="text-sm mb-2">
                <span className="font-medium">Geometry Quality: </span>
                <Badge variant="outline">
                  {bidReadiness.derived_from.geometry_quality}
                </Badge>
              </div>
            )}

            {bidReadiness.reasons_blocking.length > 0 && (
              <div className="mt-3">
                <div className="font-medium text-sm mb-1">Blocking Issues:</div>
                <ul className="list-disc list-inside text-sm space-y-1">
                  {bidReadiness.reasons_blocking.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}

            {bidReadiness.warnings.length > 0 && (
              <div className="mt-3">
                <div className="font-medium text-sm mb-1">Warnings:</div>
                <ul className="list-disc list-inside text-sm space-y-1">
                  {bidReadiness.warnings.map((warning, idx) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Phase 10.13A: Action buttons - hidden in print */}
        {!isPrintMode && (
          <div className="no-print mb-6 flex gap-2 justify-end flex-wrap">
            {/* Download Proposal PDF CTA with status */}
            <Button
              onClick={async () => {
                if (proposalPdfStatus === "ready") {
                  const url = `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/proposal.pdf`;
                  window.open(url, "_blank");
                } else {
                  // Generate PDF
                  setProposalPdfStatus("generating");
                  try {
                    await api.generateProposalPdf(projectId);
                    // Check again after a delay
                    setTimeout(async () => {
                      try {
                        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/proposal.pdf`, {
                          method: "HEAD",
                        });
                        setProposalPdfStatus(response.ok ? "ready" : "error");
                      } catch {
                        setProposalPdfStatus("error");
                      }
                    }, 3000);
                  } catch (err) {
                    setProposalPdfStatus("error");
                  }
                }
              }}
              variant="default"
              disabled={proposalPdfStatus === "generating"}
              className="min-w-[180px]"
            >
              {proposalPdfStatus === "generating" ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating PDF...
                </>
              ) : proposalPdfStatus === "ready" ? (
                <>
                  <Download className="h-4 w-4 mr-2" />
                  Download Proposal PDF
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4 mr-2" />
                  Generate Proposal PDF
                </>
              )}
            </Button>
            {proposalPdfStatus === "ready" && (
              <Badge variant="secondary" className="self-center">
                PDF Ready
              </Badge>
            )}
            <Button onClick={handlePrint} variant="outline">
              <Printer className="h-4 w-4 mr-2" />
              Print / Save PDF
            </Button>
            <Button
              onClick={() => handleDownloadJson("bid_proposal")}
              variant="outline"
            >
              <Download className="h-4 w-4 mr-2" />
              Download Bid JSON
            </Button>
            <Button
              onClick={() => handleDownloadJson("model_3d")}
              variant="outline"
            >
              <FileJson className="h-4 w-4 mr-2" />
              Download Model JSON
            </Button>
          </div>
        )}

        {/* Phase 10.13A: Print header */}
        <div className="print-header print-only">
          Construction Bid Proposal
        </div>

        {/* Phase 10.13A: Print footer */}
        <div className="print-footer print-only">
          Project ID: {bidProposal.project_id} | Profile: {pricingProfile?.profile_id || "N/A"} | {bidReadiness?.readiness_stamp_text || ""}
        </div>

        {/* Proposal Content */}
        <div className="bg-white shadow-sm rounded-lg p-8 print:shadow-none print:pt-16 print:pb-16">
          {/* Phase 10.13A: Header with improved typography */}
          <div className="mb-10 print-avoid-break">
            <h1 className="text-4xl font-bold mb-4">Construction Bid Proposal</h1>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-700">
              <div>
                <strong className="text-gray-900">Project ID:</strong> {bidProposal.project_id}
              </div>
              {pricingProfile && (
                <div>
                  <strong className="text-gray-900">Pricing Profile:</strong> {pricingProfile.profile_id} ({pricingProfile.label})
                </div>
              )}
              <div>
                <strong className="text-gray-900">Project:</strong> {projectName}
              </div>
              <div>
                <strong className="text-gray-900">Address:</strong> {projectAddress}
              </div>
              <div>
                <strong className="text-gray-900">Date:</strong> {generatedDate}
              </div>
            </div>
            
            {/* Legend (Phase 9.5) */}
            <div className="mt-4 p-3 bg-gray-50 border rounded text-xs print-avoid-break">
              <div className="font-semibold mb-2">Line Item Status Icons:</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span>Verified</span>
                </div>
                <div className="flex items-center gap-1">
                  <RotateCcw className="h-3 w-3 text-blue-600" />
                  <span>Auto-verified</span>
                </div>
                <div className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3 text-amber-600" />
                  <span>Review recommended</span>
                </div>
              </div>
            </div>
          </div>

                   {/* Phase 10.13A: Executive Summary with improved typography */}
                   <Card className="mb-8 print-avoid-break proposal-section">
                     <CardHeader className="pb-4">
                       <CardTitle className="text-2xl font-bold">
                         Executive Summary
                       </CardTitle>
                     </CardHeader>
            <CardContent>
              {proposalSections ? (
                <div className="space-y-4">
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Total Bid Amount</div>
                    <div className="text-3xl font-bold">
                      ${proposalSections.executive_summary.total_bid_amount.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Scope Summary</div>
                    <p className="text-sm">{proposalSections.executive_summary.scope_summary}</p>
                  </div>
                  {proposalSections.executive_summary.key_highlights.length > 0 && (
                    <div>
                      <div className="text-sm text-gray-600 mb-2">Key Highlights</div>
                      <ul className="list-disc list-inside space-y-1 text-sm">
                        {proposalSections.executive_summary.key_highlights.map((highlight, idx) => (
                          <li key={idx}>{highlight}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Total Bid Amount</div>
                    <div className="text-3xl font-bold">
                      ${bidProposal.summary.total_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <span className="text-sm text-gray-600">Estimate Mode: </span>
                      <Badge
                        variant={bidProposal.estimate_mode === "bid_ready" ? "default" : "secondary"}
                      >
                        {bidProposal.estimate_mode === "bid_ready" ? "Bid Ready" : "Conceptual"}
                      </Badge>
                      {!bidProposal.bid_ready && (
                        <Badge variant="destructive" className="ml-2">
                          Not Ready
                        </Badge>
                      )}
                    </div>
                    {validationReport && (
                      <div>
                        <span className="text-sm text-gray-600">Validation: </span>
                        <Badge variant={validationReport.passed ? "default" : "destructive"}>
                          {validationReport.passed ? "Passed" : "Failed"} (
                          {(validationReport.score * 100).toFixed(0)}%)
                        </Badge>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Phase 10.9A: Contractor-style sections rendering */}
          {proposalSections ? (
            <>
              {/* Scope Sections */}
              {proposalSections.scope_sections.map((section, sectionIdx) => {
                const sectionLineItems = section.line_item_ids
                  .map((id) => bidProposal.line_items[parseInt(id)])
                  .filter(Boolean);

                return (
                  <Card key={sectionIdx} className="mb-10 print-page-break print-avoid-break proposal-section">
                    <CardHeader className="pb-4">
                      <div className="flex items-start justify-between">
                        <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">{section.title}</CardTitle>
                        {section.flags.length > 0 && (
                          <div className="flex gap-1 flex-wrap">
                            {section.flags.map((flag, flagIdx) => (
                              <Badge
                                key={flagIdx}
                                variant={
                                  flag.includes("heuristic") || flag.includes("estimated")
                                    ? "secondary"
                                    : flag.includes("recovered")
                                    ? "default"
                                    : "outline"
                                }
                                className="text-xs"
                              >
                                {flag.replace(/_/g, " ")}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Narrative */}
                      <p className="text-sm text-gray-700">{section.narrative}</p>

                      {/* Line Items Table */}
                      {sectionLineItems.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-sm">
                            <thead>
                              <tr className="border-b bg-gray-50">
                                <th className="text-left p-2">Description</th>
                                <th className="text-right p-2">Quantity</th>
                                <th className="text-right p-2">Unit</th>
                                <th className="text-right p-2">Unit Cost</th>
                                <th className="text-right p-2">Total</th>
                                <th className="text-left p-2">Source</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sectionLineItems.map((item, idx) => (
                                <tr key={idx} className="border-b">
                                  <td className="p-2">
                                    <div>{item.description}</div>
                                    {item.basis && (
                                      <div className="text-xs text-gray-500 mt-1">{item.basis}</div>
                                    )}
                                  </td>
                                  <td className="text-right p-2">
                                    {item.quantity !== null
                                      ? item.quantity.toLocaleString(undefined, {
                                          maximumFractionDigits: 2,
                                        })
                                      : "—"}
                                  </td>
                                  <td className="text-right p-2">{item.unit || "—"}</td>
                                  <td className="text-right p-2">
                                    {item.unit_cost !== null
                                      ? `$${item.unit_cost.toLocaleString(undefined, {
                                          minimumFractionDigits: 2,
                                          maximumFractionDigits: 2,
                                        })}`
                                      : "—"}
                                  </td>
                                  <td className="text-right p-2 font-medium">
                                    ${item.total_cost.toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                  </td>
                                  <td className="text-left p-2">
                                    {item.quantity_source && (
                                      <Badge variant="outline" className="text-xs">
                                        {getTerm(item.quantity_source)}
                                      </Badge>
                                    )}
                                  </td>
                                </tr>
                              ))}
                              <tr className="border-t-2 font-semibold">
                                <td colSpan={4} className="p-2 text-right">
                                  Section Subtotal:
                                </td>
                                <td className="text-right p-2">
                                  $
                                  {sectionLineItems
                                    .reduce((sum, item) => sum + item.total_cost, 0)
                                    .toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                </td>
                                <td></td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      )}

                      {/* Evidence Links */}
                      {section.evidence_refs.length > 0 && (
                        <div className="mt-4">
                          <div className="text-sm font-medium mb-2">Evidence References</div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleEvidenceClick(section.evidence_refs, section.title)}
                            className="no-print"
                          >
                            <ExternalLink className="h-3 w-3 mr-2" />
                            View Evidence ({section.evidence_refs.length} reference{section.evidence_refs.length !== 1 ? "s" : ""})
                          </Button>
                          <div className="text-xs text-gray-500 mt-1 print-only">
                            {section.evidence_refs.map((ref, refIdx) => (
                              <span key={refIdx}>
                                Page {ref.page_number}
                                {ref.snippet && `: ${ref.snippet.substring(0, 50)}${ref.snippet.length > 50 ? "..." : ""}`}
                                {refIdx < section.evidence_refs.length - 1 ? "; " : ""}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Detail References */}
                      {section.detail_refs.length > 0 && (
                        <div className="mt-2">
                          <div className="text-sm font-medium mb-1">Detail References</div>
                          <div className="flex flex-wrap gap-1">
                            {section.detail_refs.map((detailId, detailIdx) => (
                              <Badge key={detailIdx} variant="outline" className="text-xs">
                                {detailId}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}

              {/* Logistics Section */}
              {proposalSections.logistics_section.line_item_ids.length > 0 && (
                <Card className="mb-10 print-page-break print-avoid-break proposal-section">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">{proposalSections.logistics_section.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-gray-700">{proposalSections.logistics_section.narrative}</p>
                    {proposalSections.logistics_section.evidence_refs.length > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          handleEvidenceClick(
                            proposalSections.logistics_section.evidence_refs,
                            proposalSections.logistics_section.title
                          )
                        }
                        className="no-print"
                      >
                        <ExternalLink className="h-3 w-3 mr-2" />
                        View Evidence
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Permits & Inspections Section */}
              {proposalSections.permits_inspections_section.line_item_ids.length > 0 && (
                <Card className="mb-10 print-page-break print-avoid-break proposal-section">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">{proposalSections.permits_inspections_section.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-gray-700">
                      {proposalSections.permits_inspections_section.narrative}
                    </p>
                    {proposalSections.permits_inspections_section.evidence_refs.length > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          handleEvidenceClick(
                            proposalSections.permits_inspections_section.evidence_refs,
                            proposalSections.permits_inspections_section.title
                          )
                        }
                        className="no-print"
                      >
                        <ExternalLink className="h-3 w-3 mr-2" />
                        View Evidence
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Phase 10.13A: Exclusions & Assumptions with improved typography */}
              <Card className="mb-10 print-page-break print-avoid-break proposal-section">
                <CardHeader className="pb-4">
                  <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">Exclusions & Assumptions</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <h4 className="font-semibold mb-2">Exclusions</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                        {proposalSections.exclusions.map((exclusion, idx) => (
                          <li key={idx}>{exclusion}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4 className="font-semibold mb-2">Assumptions</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                        {proposalSections.assumptions.map((assumption, idx) => (
                          <li key={idx}>{assumption}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Phase 10.13A: Schedule & Payment with improved typography */}
              <Card className="mb-10 print-page-break print-avoid-break proposal-section">
                <CardHeader className="pb-4">
                  <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">Schedule & Payment Terms</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <h4 className="font-semibold mb-2">Project Schedule</h4>
                      {proposalSections.schedule.estimated_duration_weeks && (
                        <p className="text-sm text-gray-700 mb-2">
                          Estimated Duration: {proposalSections.schedule.estimated_duration_weeks} weeks
                        </p>
                      )}
                      {proposalSections.schedule.start_conditions.length > 0 && (
                        <div>
                          <div className="text-sm font-medium mb-1">Start Conditions:</div>
                          <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                            {proposalSections.schedule.start_conditions.map((condition, idx) => (
                              <li key={idx}>{condition}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <div>
                      <h4 className="font-semibold mb-2">Payment Schedule</h4>
                      <ul className="space-y-2 text-sm text-gray-700">
                        {proposalSections.payment_schedule.milestone_1 && (
                          <li>{proposalSections.payment_schedule.milestone_1}</li>
                        )}
                        {proposalSections.payment_schedule.milestone_2 && (
                          <li>{proposalSections.payment_schedule.milestone_2}</li>
                        )}
                        {proposalSections.payment_schedule.milestone_3 && (
                          <li>{proposalSections.payment_schedule.milestone_3}</li>
                        )}
                        {proposalSections.payment_schedule.final_payment && (
                          <li>{proposalSections.payment_schedule.final_payment}</li>
                        )}
                      </ul>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Coverage & Warranty (Contractor Declared) */}
              <Card id="coverage-warranty" className="mb-10 print-page-break print-avoid-break proposal-section">
                <CardHeader className="pb-4">
                  <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">
                    Coverage & Warranty (Contractor Declared)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {coverageDeclarations ? (
                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <h4 className="font-semibold mb-3">Insurance</h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-700">General Liability:</span>
                            <Badge variant={coverageDeclarations.insurance.general_liability_status === "declared" ? "default" : "secondary"}>
                              {coverageDeclarations.insurance.general_liability_status === "declared" ? "Declared" : "Not Declared"}
                            </Badge>
                          </div>
                          {coverageDeclarations.insurance.general_liability_limit && (
                            <div className="text-gray-600 ml-4">
                              Limit: {coverageDeclarations.insurance.general_liability_limit}
                            </div>
                          )}
                          <div className="flex justify-between">
                            <span className="text-gray-700">Workers Comp:</span>
                            <Badge variant={coverageDeclarations.insurance.workers_comp_status === "declared" ? "default" : "secondary"}>
                              {coverageDeclarations.insurance.workers_comp_status === "declared" ? "Declared" : "Not Declared"}
                            </Badge>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-700">Umbrella:</span>
                            <Badge variant={coverageDeclarations.insurance.umbrella_status === "declared" ? "default" : "secondary"}>
                              {coverageDeclarations.insurance.umbrella_status === "declared" ? "Declared" : "Not Declared"}
                            </Badge>
                          </div>
                          {coverageDeclarations.insurance.umbrella_limit && (
                            <div className="text-gray-600 ml-4">
                              Limit: {coverageDeclarations.insurance.umbrella_limit}
                            </div>
                          )}
                          <div className="flex justify-between">
                            <span className="text-gray-700">Bond:</span>
                            <Badge variant={
                              coverageDeclarations.insurance.bond_status === "available" ? "default" :
                              coverageDeclarations.insurance.bond_status === "not_available" ? "destructive" : "secondary"
                            }>
                              {coverageDeclarations.insurance.bond_status === "available" ? "Available" :
                               coverageDeclarations.insurance.bond_status === "not_available" ? "Not Available" : "Not Declared"}
                            </Badge>
                          </div>
                        </div>
                      </div>
                      <div>
                        <h4 className="font-semibold mb-3">Warranty</h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-700">Workmanship:</span>
                            <Badge variant={coverageDeclarations.warranty.workmanship_status === "declared" ? "default" : "secondary"}>
                              {coverageDeclarations.warranty.workmanship_status === "declared" ? "Declared" : "Not Declared"}
                            </Badge>
                          </div>
                          {coverageDeclarations.warranty.workmanship_duration && (
                            <div className="text-gray-600 ml-4">
                              Duration: {coverageDeclarations.warranty.workmanship_duration}
                            </div>
                          )}
                          <div className="flex justify-between">
                            <span className="text-gray-700">Materials:</span>
                            <Badge variant={coverageDeclarations.warranty.materials_status === "declared" ? "default" : "secondary"}>
                              {coverageDeclarations.warranty.materials_status === "declared" ? "Declared" : "Not Declared"}
                            </Badge>
                          </div>
                          {coverageDeclarations.warranty.materials_basis && (
                            <div className="text-gray-600 ml-4">
                              Basis: {coverageDeclarations.warranty.materials_basis}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 italic">
                      <Alert>
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                          Coverage & Warranty declarations not yet generated. This section will show contractor-declared insurance and warranty information when available.
                        </AlertDescription>
                      </Alert>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Notes */}
              {/* Phase 10.13A: General Notes with improved typography */}
              {proposalSections.notes.length > 0 && (
                <Card className="mb-10 print-page-break print-avoid-break proposal-section">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-2xl font-bold pb-2 border-b border-gray-200">Additional Notes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                      {proposalSections.notes.map((note, idx) => (
                        <li key={idx}>{note}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <>

          {/* Cost by Division */}
          {Object.keys(bidProposal.summary.cost_by_division).length > 0 && (
            <Card className="mb-6 print-avoid-break">
              <CardHeader>
                <CardTitle>Cost by Division</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">Division</th>
                        <th className="text-right p-2">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(bidProposal.summary.cost_by_division)
                        .sort(([, a], [, b]) => b - a)
                        .map(([division, amount]) => (
                          <tr key={division} className="border-b">
                            <td className="p-2">{division}</td>
                            <td className="text-right p-2">
                              ${amount.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                          </tr>
                        ))}
                      <tr className="border-t-2 font-bold">
                        <td className="p-2">Total</td>
                        <td className="text-right p-2">
                          ${bidProposal.summary.total_cost.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Detailed Line Items */}
          {bidProposal.line_items.length > 0 && (
            <Card className="mb-6 print-page-break print-avoid-break">
              <CardHeader>
                <CardTitle>Detailed Line Items</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.entries(itemsByDivision).map(([division, items]) => (
                  <div key={division} className="mb-6 print-avoid-break">
                    <h3 className="font-semibold text-lg mb-2">{division}</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-sm">
                        <thead>
                          <tr className="border-b bg-gray-50">
                            <th className="text-left p-2">Description</th>
                            <th className="text-right p-2">Quantity</th>
                            <th className="text-right p-2">Unit</th>
                            <th className="text-right p-2">Unit Cost</th>
                            <th className="text-right p-2">Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {items.map((item, idx) => {
                            // Determine icon for this line item (Phase 9.5)
                            const getStatusIcon = () => {
                              if (item.quantity_source === "explicit_takeoff" || item.quantity_source === "from_drawing" || item.quantity_source === "from_schedule") {
                                return <span title="Verified"><CheckCircle2 className="h-4 w-4 text-emerald-600 inline mr-1" /></span>;
                              }
                              if (item.quantity_source === "recovered" || item.quantity_source === "computed_from_dimensions") {
                                return <span title="Auto-verified"><RotateCcw className="h-4 w-4 text-blue-600 inline mr-1" /></span>;
                              }
                              if (item.quantity_source === "heuristic" || item.quantity_source === "unknown") {
                                return <span title="Review recommended"><AlertTriangle className="h-4 w-4 text-amber-600 inline mr-1" /></span>;
                              }
                              return null;
                            };

                            return (
                            <tr key={idx} className="border-b">
                              <td className="p-2">
                                <div className="flex items-start gap-1">
                                  {getStatusIcon()}
                                  <span>{item.description}</span>
                                </div>
                                {item.quantity_source && (
                                  <div className="mt-1">
                                    <Badge variant="outline" className="text-xs">
                                      {getTerm(item.quantity_source)}
                                    </Badge>
                                    {item.quantity_confidence !== null &&
                                      item.quantity_confidence !== undefined && (
                                        <span className="text-xs text-gray-500 ml-2">
                                          {(item.quantity_confidence * 100).toFixed(0)}% confidence
                                        </span>
                                      )}
                                  </div>
                                )}
                                <div className="text-xs text-gray-500 mt-1">{item.basis}</div>
                              </td>
                              <td className="text-right p-2">
                                {item.quantity !== null
                                  ? item.quantity.toLocaleString(undefined, {
                                      maximumFractionDigits: 2,
                                    })
                                  : "—"}
                              </td>
                              <td className="text-right p-2">{item.unit || "—"}</td>
                              <td className="text-right p-2">
                                {item.unit_cost !== null
                                  ? `$${item.unit_cost.toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}`
                                  : "—"}
                              </td>
                              <td className="text-right p-2 font-medium">
                                ${item.total_cost.toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                              </td>
                            </tr>
                            );
                          })}
                          <tr className="border-t font-semibold">
                            <td colSpan={4} className="p-2 text-right">
                              {division} Subtotal:
                            </td>
                            <td className="text-right p-2">
                              $
                              {items
                                .reduce((sum, item) => sum + item.total_cost, 0)
                                .toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Allowances */}
          {bidProposal.allowances.length > 0 && (
            <Card className="mb-6 print-avoid-break">
              <CardHeader>
                <CardTitle>Allowances</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {bidProposal.allowances.map((allowance, idx) => (
                    <div key={idx} className="border-b pb-3">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-medium">{allowance.name}</div>
                          <div className="text-sm text-gray-600 mt-1">{allowance.notes}</div>
                        </div>
                        <div className="text-right font-medium">
                          ${allowance.amount.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

              {/* Legacy rendering continues below */}
            </>
          )}

          {/* Legacy Rendering (when proposal_sections not available) */}
          {!proposalSections && (
            <>
              {/* Cost by Division */}
              {Object.keys(bidProposal.summary.cost_by_division).length > 0 && (
                <Card className="mb-6 print-avoid-break">
                  <CardHeader>
                    <CardTitle>Cost by Division</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left p-2">Division</th>
                            <th className="text-right p-2">Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(bidProposal.summary.cost_by_division)
                            .sort(([, a], [, b]) => b - a)
                            .map(([division, amount]) => (
                              <tr key={division} className="border-b">
                                <td className="p-2">{division}</td>
                                <td className="text-right p-2">
                                  ${amount.toLocaleString(undefined, {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>
                              </tr>
                            ))}
                          <tr className="border-t-2 font-bold">
                            <td className="p-2">Total</td>
                            <td className="text-right p-2">
                              ${bidProposal.summary.total_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Detailed Line Items */}
              {bidProposal.line_items.length > 0 && (
                <Card className="mb-6 print-page-break print-avoid-break">
                  <CardHeader>
                    <CardTitle>Detailed Line Items</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {Object.entries(itemsByDivision).map(([division, items]) => (
                      <div key={division} className="mb-6 print-avoid-break">
                        <h3 className="font-semibold text-lg mb-2">{division}</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-sm">
                            <thead>
                              <tr className="border-b bg-gray-50">
                                <th className="text-left p-2">Description</th>
                                <th className="text-right p-2">Quantity</th>
                                <th className="text-right p-2">Unit</th>
                                <th className="text-right p-2">Unit Cost</th>
                                <th className="text-right p-2">Total</th>
                              </tr>
                            </thead>
                            <tbody>
                              {items.map((item, idx) => {
                                // Determine icon for this line item (Phase 9.5)
                                const getStatusIcon = () => {
                                  if (item.quantity_source === "explicit_takeoff" || item.quantity_source === "from_drawing" || item.quantity_source === "from_schedule") {
                                    return <span title="Verified"><CheckCircle2 className="h-4 w-4 text-emerald-600 inline mr-1" /></span>;
                                  }
                                  if (item.quantity_source === "recovered" || item.quantity_source === "computed_from_dimensions") {
                                    return <span title="Auto-verified"><RotateCcw className="h-4 w-4 text-blue-600 inline mr-1" /></span>;
                                  }
                                  if (item.quantity_source === "heuristic" || item.quantity_source === "unknown") {
                                    return <span title="Review recommended"><AlertTriangle className="h-4 w-4 text-amber-600 inline mr-1" /></span>;
                                  }
                                  return null;
                                };

                                return (
                                <tr key={idx} className="border-b">
                                  <td className="p-2">
                                    <div className="flex items-start gap-1">
                                      {getStatusIcon()}
                                      <span>{item.description}</span>
                                    </div>
                                    {item.quantity_source && (
                                      <div className="mt-1">
                                        <Badge variant="outline" className="text-xs">
                                          {getTerm(item.quantity_source)}
                                        </Badge>
                                        {item.quantity_confidence !== null &&
                                          item.quantity_confidence !== undefined && (
                                            <span className="text-xs text-gray-500 ml-2">
                                              {(item.quantity_confidence * 100).toFixed(0)}% confidence
                                            </span>
                                          )}
                                      </div>
                                    )}
                                    <div className="text-xs text-gray-500 mt-1">{item.basis}</div>
                                  </td>
                                  <td className="text-right p-2">
                                    {item.quantity !== null
                                      ? item.quantity.toLocaleString(undefined, {
                                          maximumFractionDigits: 2,
                                        })
                                      : "—"}
                                  </td>
                                  <td className="text-right p-2">{item.unit || "—"}</td>
                                  <td className="text-right p-2">
                                    {item.unit_cost !== null
                                      ? `$${item.unit_cost.toLocaleString(undefined, {
                                          minimumFractionDigits: 2,
                                          maximumFractionDigits: 2,
                                        })}`
                                      : "—"}
                                  </td>
                                  <td className="text-right p-2 font-medium">
                                    ${item.total_cost.toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                  </td>
                                </tr>
                                );
                              })}
                              <tr className="border-t font-semibold">
                                <td colSpan={4} className="p-2 text-right">
                                  {division} Subtotal:
                                </td>
                                <td className="text-right p-2">
                                  $
                                  {items
                                    .reduce((sum, item) => sum + item.total_cost, 0)
                                    .toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Allowances */}
              {bidProposal.allowances.length > 0 && (
                <Card className="mb-6 print-avoid-break">
                  <CardHeader>
                    <CardTitle>Allowances</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {bidProposal.allowances.map((allowance, idx) => (
                        <div key={idx} className="border-b pb-3">
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="font-medium">{allowance.name}</div>
                              <div className="text-sm text-gray-600 mt-1">{allowance.notes}</div>
                            </div>
                            <div className="text-right font-medium">
                              ${allowance.amount.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Clarifications */}
              {bidProposal.clarifications.length > 0 && (
            <Card className="mb-6 print-page-break print-avoid-break">
              <CardHeader>
                <CardTitle>Clarifications, Exclusions & Assumptions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {bidProposal.clarifications.map((clarification, idx) => (
                    <div key={idx} className="border-l-4 pl-3 py-1">
                      <div className="flex items-start gap-2">
                        <Badge
                          variant={
                            clarification.severity === "critical"
                              ? "destructive"
                              : clarification.severity === "warning"
                              ? "default"
                              : "secondary"
                          }
                          className="text-xs"
                        >
                          {clarification.severity.toUpperCase()}
                        </Badge>
                        <p className="text-sm">{clarification.text}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

            </>
          )}

          {/* Trust & Disclosure Footer (Phase 9.4) */}
          <div className="mt-8 print-page-break print-avoid-break border-t pt-6">
            <div className="text-xs space-y-2 text-gray-600">
              <div className="font-semibold text-gray-900">Trust & Scope</div>
              <div>
                <strong>What this bid includes:</strong> Line items with quantities and unit costs, drawing references for each item, 3D geometry visualization, cost breakdown by division.
              </div>
              <div>
                <strong>What this bid does NOT include:</strong> Field verification or site visits, permits or regulatory approvals, contingencies or markups, final engineering review.
              </div>
              <div className="italic text-gray-700 border-l-2 border-amber-300 pl-2 mt-2">
                <strong>Disclaimer:</strong> This bid is evidence-backed but does not replace field verification. All quantities and costs should be reviewed by a qualified professional before submission.
              </div>
            </div>
          </div>

          {/* Evidence Highlights (Phase 10.4) - Only in print mode with highlights=1 */}
          {showHighlights && Object.keys(evidenceByPage).length > 0 && (
            <div className="mt-8 print-page-break print-avoid-break border-t pt-6">
              <h2 className="text-2xl font-bold mb-4">Evidence Highlights</h2>
              <p className="text-sm text-gray-600 mb-4">
                Blue highlighted regions indicate where line item information was found in the source documents.
              </p>
              {Object.keys(evidenceByPage)
                .map(Number)
                .sort((a, b) => a - b)
                .map((pageNum) => renderPageWithHighlights(pageNum))}
            </div>
          )}

          {/* Signature Block */}
          <div className="mt-12 print-page-break print-avoid-break">
            <div className="border-t pt-6">
              <div className="grid grid-cols-2 gap-8">
                <div>
                  <div className="border-b mb-2 pb-1">Contractor Signature</div>
                  <div className="text-sm text-gray-500">Date: _______________</div>
                </div>
                <div>
                  <div className="border-b mb-2 pb-1">Owner/Representative Signature</div>
                  <div className="text-sm text-gray-500">Date: _______________</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Evidence Drawer */}
      <EvidenceDrawer
        open={evidenceDrawerOpen}
        onOpenChange={setEvidenceDrawerOpen}
        title={selectedEvidenceTitle}
        evidence={selectedEvidence}
        projectId={projectId}
        initialPage={selectedEvidence.length > 0 ? selectedEvidence[0].page_number : undefined}
      />
    </>
  );
}
