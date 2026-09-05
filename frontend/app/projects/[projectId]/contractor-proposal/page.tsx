"use client";

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, AlertCircle } from "lucide-react";

interface ContractorBid {
  project_id: string;
  bid_mode: "contractor";
  total_bid: number;
  subtotals: Record<string, number>;
  sections: Array<{
    section_id: string;
    title: string;
    division: string | null;
    line_items: Array<{
      item_id: string;
      title: string;
      division: string | null;
      quantity: number | null;
      unit: string | null;
      unit_cost: number | null;
      total_cost: number;
      basis: string;
      notes: string | null;
    }>;
    subtotal: number;
  }>;
  permits_and_inspections: Array<{
    item_id: string;
    title: string;
    division: string | null;
    quantity: number | null;
    unit: string | null;
    unit_cost: number | null;
    total_cost: number;
    basis: string;
    notes: string | null;
  }>;
  logistics: Array<{
    item_id: string;
    title: string;
    division: string | null;
    quantity: number | null;
    unit: string | null;
    unit_cost: number | null;
    total_cost: number;
    basis: string;
    notes: string | null;
  }>;
  exclusions: string[];
  assumptions: string[];
  payment_schedule: Array<{
    milestone_id: string;
    title: string;
    percentage: number;
    amount: number;
    trigger: string;
  }> | null;
  schedule: {
    estimated_start_date: string | null;
    estimated_duration_days: number | null;
    estimated_completion_date: string | null;
  } | null;
}

interface DocumentAnalysis {
  project_name?: string;
  project_address?: string;
  project_location?: string;
}

export default function ContractorProposalPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const projectId = params.projectId as string;
  const isPrintMode = searchParams.get("print") === "1";

  const [contractorBid, setContractorBid] = useState<ContractorBid | null>(null);
  const [documentAnalysis, setDocumentAnalysis] = useState<DocumentAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        // Load contractor bid (required)
        const bidData = await api.getContractorBid(projectId);
        if (!bidData) {
          throw new Error("Contractor bid not found");
        }
        setContractorBid(bidData);

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

        setError(null);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load contractor proposal data.");
        }
        console.error("Load error:", err);
      } finally {
        setLoading(false);
        // Mark proposal as ready for PDF generation
        if (typeof document !== "undefined") {
          const marker = document.getElementById("contractor-proposal-ready");
          if (marker) {
            marker.setAttribute("data-ready", "true");
          }
        }
      }
    };

    loadData();
  }, [projectId]);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  if (error || !contractorBid) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error || "Contractor bid not found. Please generate contractor bid first."}
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
  const generatedDate = new Date((contractorBid as any).created_at || new Date().toISOString()).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <>
      {/* Print-only styles */}
      <style jsx global>{`
        @media print {
          .no-print {
            display: none !important;
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
          }
          .container {
            max-width: 100% !important;
            padding: 0 !important;
          }
        }
        @page {
          margin: 0.75in;
          size: letter;
        }
      `}</style>

      {/* Proposal-ready marker for Playwright */}
      <div id="contractor-proposal-ready" data-ready="false" style={{ display: "none" }} />

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        {/* Readiness Banner (Phase 9.6) */}
        <div className="mb-6 p-4 rounded-lg border-2 bg-amber-50 border-amber-500 text-amber-900 print-avoid-break">
          <h2 className="text-2xl font-bold mb-2">
            CONTRACTOR BID — REVIEW REQUIRED
          </h2>
          <p className="text-sm">
            This contractor bid has been synthesized from conceptual estimates and contractor profile data.
            Review all sections, exclusions, and assumptions before submission.
          </p>
        </div>

        {/* Proposal Content */}
        <div className="bg-white shadow-sm rounded-lg p-8 print:shadow-none">
          {/* Header */}
          <div className="mb-8 print-avoid-break">
            <h1 className="text-3xl font-bold mb-2">Contractor Bid Proposal</h1>
            <div className="space-y-1 text-sm text-gray-600">
              <div>
                <strong>Project ID:</strong> {contractorBid.project_id}
              </div>
              <div>
                <strong>Project:</strong> {projectName}
              </div>
              <div>
                <strong>Address:</strong> {projectAddress}
              </div>
              <div>
                <strong>Date:</strong> {generatedDate}
              </div>
              <div>
                <strong>Bid Mode:</strong> <Badge variant="secondary">CONTRACTOR (SYNTHESIZED)</Badge>
              </div>
            </div>
          </div>

          {/* Executive Summary */}
          <div className="mb-8 print-avoid-break">
            <h2 className="text-2xl font-bold mb-4">Executive Summary</h2>
            <Card>
              <CardContent className="pt-6">
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-lg font-semibold">Total Bid Amount:</span>
                    <span className="text-3xl font-bold">
                      ${contractorBid.total_bid.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                    {Object.entries(contractorBid.subtotals).map(([key, value]) => (
                      <div key={key} className="flex justify-between">
                        <span className="capitalize text-muted-foreground">{key.replace(/_/g, " ")}:</span>
                        <span className="font-medium">
                          ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Detailed Scope Sections */}
          {contractorBid.sections.map((section) => (
            <div key={section.section_id} className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">{section.title}</h2>
              {section.division && (
                <p className="text-sm text-muted-foreground mb-4">Division: {section.division}</p>
              )}
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-4">
                    {section.line_items.map((item) => (
                      <div key={item.item_id} className="border-b pb-4 last:border-0">
                        <div className="flex justify-between items-start mb-2">
                          <div className="flex-1">
                            <h3 className="font-semibold">{item.title}</h3>
                            {item.notes && (
                              <p className="text-sm text-muted-foreground mt-1">{item.notes}</p>
                            )}
                          </div>
                          <div className="text-right ml-4">
                            <div className="font-bold">
                              ${item.total_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                            {item.quantity !== null && item.unit_cost !== null && (
                              <div className="text-sm text-muted-foreground">
                                {item.quantity.toLocaleString()} {item.unit} @ ${item.unit_cost.toFixed(2)}
                              </div>
                            )}
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground">{item.basis}</p>
                      </div>
                    ))}
                    <div className="flex justify-between items-center pt-4 border-t font-semibold">
                      <span>Section Subtotal:</span>
                      <span>
                        ${section.subtotal.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          ))}

          {/* Permits & Inspections */}
          {contractorBid.permits_and_inspections.length > 0 && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Permits & Inspections</h2>
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-4">
                    {contractorBid.permits_and_inspections.map((item) => (
                      <div key={item.item_id} className="flex justify-between items-center border-b pb-4 last:border-0">
                        <div>
                          <h3 className="font-semibold">{item.title}</h3>
                          <p className="text-xs text-muted-foreground mt-1">{item.basis}</p>
                        </div>
                        <div className="font-bold">
                          ${item.total_cost.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Logistics */}
          {contractorBid.logistics.length > 0 && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Logistics</h2>
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-4">
                    {contractorBid.logistics.map((item) => (
                      <div key={item.item_id} className="flex justify-between items-center border-b pb-4 last:border-0">
                        <div className="flex-1">
                          <h3 className="font-semibold">{item.title}</h3>
                          {item.quantity !== null && item.unit && (
                            <p className="text-sm text-muted-foreground">
                              {item.quantity.toLocaleString()} {item.unit}
                            </p>
                          )}
                          <p className="text-xs text-muted-foreground mt-1">{item.basis}</p>
                        </div>
                        <div className="font-bold">
                          ${item.total_cost.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Payment Schedule */}
          {contractorBid.payment_schedule && contractorBid.payment_schedule.length > 0 && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Payment Schedule</h2>
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-4">
                    {contractorBid.payment_schedule.map((milestone) => (
                      <div key={milestone.milestone_id} className="flex justify-between items-center border-b pb-4 last:border-0">
                        <div>
                          <h3 className="font-semibold">{milestone.title}</h3>
                          <p className="text-sm text-muted-foreground">{milestone.trigger}</p>
                        </div>
                        <div className="text-right">
                          <div className="font-bold">
                            ${milestone.amount.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {milestone.percentage.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Schedule */}
          {contractorBid.schedule && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Project Schedule</h2>
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-2 text-sm">
                    {contractorBid.schedule.estimated_start_date && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Estimated Start:</span>
                        <span className="font-medium">{contractorBid.schedule.estimated_start_date}</span>
                      </div>
                    )}
                    {contractorBid.schedule.estimated_duration_days && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Estimated Duration:</span>
                        <span className="font-medium">{contractorBid.schedule.estimated_duration_days} days</span>
                      </div>
                    )}
                    {contractorBid.schedule.estimated_completion_date && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Estimated Completion:</span>
                        <span className="font-medium">{contractorBid.schedule.estimated_completion_date}</span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Exclusions */}
          {contractorBid.exclusions.length > 0 && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Exclusions</h2>
              <Card>
                <CardContent className="pt-6">
                  <ul className="list-disc list-inside space-y-2 text-sm">
                    {contractorBid.exclusions.map((exclusion, idx) => (
                      <li key={idx} className="text-muted-foreground">{exclusion}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Assumptions */}
          {contractorBid.assumptions.length > 0 && (
            <div className="mb-8 print-page-break print-avoid-break">
              <h2 className="text-2xl font-bold mb-4">Assumptions</h2>
              <Card>
                <CardContent className="pt-6">
                  <ul className="list-disc list-inside space-y-2 text-sm">
                    {contractorBid.assumptions.map((assumption, idx) => (
                      <li key={idx} className="text-muted-foreground">{assumption}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Footer */}
          <div className="mt-8 print-page-break print-avoid-break border-t pt-6">
            <div className="text-xs space-y-2 text-gray-600">
              <div className="font-semibold text-gray-900">Contractor Bid — Review Required</div>
              <div>
                This contractor bid has been synthesized from conceptual estimates, expanded scope, labor breakdown, and contractor profile data.
                All quantities, costs, and assumptions should be reviewed by a qualified professional before submission.
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

