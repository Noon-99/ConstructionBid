/** Contractor Walkthrough Mode (Phase 9.2, 10.8).
 * 
 * Step-by-step guided review workflow.
 */

"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { X, ChevronRight, ChevronLeft, CheckCircle2, AlertTriangle, FileText, DollarSign, TrendingUp, Info, Layers, Eye, Download, Loader2 } from "lucide-react";
import { ProjectSummary, api, ApiError } from "@/lib/api";

interface WalkthroughModeProps {
  summary: ProjectSummary;
  totalBid?: number;
  projectId: string; // Phase 10.8: Need project ID to load data
  onClose: () => void;
  onHighlightTab?: (tab: string) => void; // Phase 10.8: Highlight relevant tab
  onSetHeatmapMode?: (mode: "cost" | null) => void; // Phase 10.8: Auto-toggle heatmap
}

type WalkthroughStep = 
  | "validation"
  | "cost_drivers"
  | "evidence_coverage"
  | "3d_heatmap"
  | "proposal";

const STEP_ORDER: WalkthroughStep[] = [
  "validation",
  "cost_drivers",
  "evidence_coverage",
  "3d_heatmap",
  "proposal",
];

interface BidReadinessV2 {
  conceptual_ready: boolean;
  contractor_ready: boolean;
  conceptual_reasons_blocking: string[];
  contractor_reasons_blocking: string[];
  conceptual_warnings: string[];
  contractor_warnings: string[];
}

interface BidProposal {
  line_items: Array<{
    description: string;
    total_cost: number;
    quantity_source?: string | null;
    confidence: number;
  }>;
}

interface Model3D {
  missing_evidence?: string[];
}

export function WalkthroughMode({ 
  summary, 
  totalBid, 
  projectId,
  onClose,
  onHighlightTab,
  onSetHeatmapMode,
}: WalkthroughModeProps) {
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [bidReadinessV2, setBidReadinessV2] = useState<BidReadinessV2 | null>(null);
  const [topCostDrivers, setTopCostDrivers] = useState<Array<{description: string; cost: number; flags: string[]}>>([]);
  const [missingEvidence, setMissingEvidence] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  // Load data for walkthrough
  useEffect(() => {
    const loadData = async () => {
      try {
        // Load bid readiness v2
        try {
          const readiness = await api.getBidReadinessV2(projectId);
          setBidReadinessV2(readiness);
        } catch (e) {
          console.warn("Could not load bid readiness v2:", e);
        }

        // Load bid proposal for top cost drivers
        try {
          const proposal = await api.getArtifact<BidProposal>(projectId, "bid_proposal");
          // Get top 5 by cost
          const sorted = [...(proposal.line_items || [])]
            .sort((a, b) => b.total_cost - a.total_cost)
            .slice(0, 5);
          
          const drivers = sorted.map(item => ({
            description: item.description,
            cost: item.total_cost,
            flags: [
              ...(item.quantity_source === "heuristic" ? ["Heuristic quantity"] : []),
              ...(item.confidence < 0.7 ? ["Low confidence"] : []),
            ],
          }));
          setTopCostDrivers(drivers);
        } catch (e) {
          console.warn("Could not load bid proposal:", e);
        }

        // Load missing evidence
        try {
          const model3d = await api.getArtifact<Model3D>(projectId, "model_3d");
          setMissingEvidence(model3d.missing_evidence || []);
        } catch (e) {
          console.warn("Could not load model_3d:", e);
        }
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId]);

  // Phase 10.8: Highlight relevant tab and auto-toggle features based on step
  useEffect(() => {
    const step = STEP_ORDER[currentStep];
    
    // Highlight relevant tab
    if (onHighlightTab) {
      switch (step) {
        case "validation":
          onHighlightTab("overview");
          break;
        case "cost_drivers":
          onHighlightTab("bid");
          break;
        case "evidence_coverage":
          onHighlightTab("evidence");
          break;
        case "3d_heatmap":
          onHighlightTab("3d");
          // Auto-toggle cost heatmap
          if (onSetHeatmapMode) {
            onSetHeatmapMode("cost");
          }
          break;
        case "proposal":
          onHighlightTab("proposal");
          break;
      }
    }

    // Cleanup: reset heatmap when leaving 3D step
    return () => {
      if (step === "3d_heatmap" && onSetHeatmapMode) {
        // Don't reset immediately, only when step changes away
      }
    };
  }, [currentStep, onHighlightTab, onSetHeatmapMode]);

  const step = STEP_ORDER[currentStep];
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === STEP_ORDER.length - 1;

  const nextStep = () => {
    if (!isLastStep) {
      setCurrentStep(currentStep + 1);
    }
  };

  const prevStep = () => {
    if (!isFirstStep) {
      setCurrentStep(currentStep - 1);
    }
  };

  const getStepContent = () => {
    switch (step) {
      case "validation":
        return {
          title: "Validation & Readiness",
          description: "Review bid readiness assessment (Phase 10.8).",
          content: (
            <div className="space-y-4">
              {loading ? (
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 border rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium">Conceptual Ready</span>
                        {bidReadinessV2?.conceptual_ready ? (
                          <CheckCircle2 className="h-5 w-5 text-green-500" />
                        ) : (
                          <AlertTriangle className="h-5 w-5 text-yellow-500" />
                        )}
                      </div>
                      {bidReadinessV2?.conceptual_reasons_blocking.length > 0 && (
                        <ul className="text-sm text-gray-600 space-y-1 mt-2">
                          {bidReadinessV2.conceptual_reasons_blocking.map((reason, idx) => (
                            <li key={idx}>• {reason}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="p-4 border rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium">Contractor Ready</span>
                        {bidReadinessV2?.contractor_ready ? (
                          <CheckCircle2 className="h-5 w-5 text-green-500" />
                        ) : (
                          <AlertTriangle className="h-5 w-5 text-yellow-500" />
                        )}
                      </div>
                      {bidReadinessV2?.contractor_reasons_blocking.length > 0 && (
                        <ul className="text-sm text-gray-600 space-y-1 mt-2">
                          {bidReadinessV2.contractor_reasons_blocking.map((reason, idx) => (
                            <li key={idx}>• {reason}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Check the Overview tab for detailed readiness scores and validation results.
                  </p>
                </>
              )}
            </div>
          ),
        };
      case "cost_drivers":
        return {
          title: "Top 5 Cost Drivers",
          description: "Review the highest-cost line items and their flags (Phase 10.8).",
          content: (
            <div className="space-y-4">
              {loading ? (
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              ) : topCostDrivers.length > 0 ? (
                <>
                  <div className="space-y-3">
                    {topCostDrivers.map((driver, idx) => (
                      <div key={idx} className="p-3 border rounded-lg">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="font-medium">{driver.description}</div>
                            <div className="text-lg font-bold text-emerald-600 mt-1">
                              ${driver.cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                          <div className="flex gap-1">
                            {driver.flags.map((flag, flagIdx) => (
                              <Badge key={flagIdx} variant="outline" className="text-xs">
                                {flag}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    See the Bid tab for complete line item breakdown and evidence links.
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Loading cost drivers...
                </p>
              )}
            </div>
          ),
        };
      case "evidence_coverage":
        return {
          title: "Evidence Coverage",
          description: "Review missing evidence list (Phase 10.8).",
          content: (
            <div className="space-y-4">
              {loading ? (
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              ) : (
                <>
                  {missingEvidence.length > 0 ? (
                    <>
                      <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                        <div className="flex items-start gap-2 mb-2">
                          <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
                          <div className="font-medium text-amber-900">
                            Missing Evidence ({missingEvidence.length} items)
                          </div>
                        </div>
                        <ul className="text-sm text-amber-700 space-y-1 mt-2">
                          {missingEvidence.map((item, idx) => (
                            <li key={idx}>• {item}</li>
                          ))}
                        </ul>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Some geometry or scope information could not be extracted. Review the Evidence tab for details.
                      </p>
                    </>
                  ) : (
                    <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
                        <div>
                          <div className="font-medium text-emerald-900">All Evidence Extracted</div>
                          <div className="text-sm text-emerald-700 mt-1">
                            No missing evidence items detected.
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ),
        };
      case "3d_heatmap":
        return {
          title: "3D Cost Heatmap",
          description: "Visualize cost distribution in 3D model (Phase 10.8).",
          content: (
            <div className="space-y-4">
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-start gap-2 mb-2">
                  <Layers className="h-5 w-5 text-blue-600 mt-0.5" />
                  <div>
                    <div className="font-medium text-blue-900">3D Heatmap Enabled</div>
                    <div className="text-sm text-blue-700 mt-1">
                      The 3D Model tab should now show cost heatmap overlay. Click on zones to see cost breakdowns.
                    </div>
                  </div>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                Navigate to the 3D Model tab to interact with the cost heatmap. Use the heatmap toggle to switch between modes.
              </p>
            </div>
          ),
        };
      case "proposal":
        return {
          title: "Proposal Preview & PDF",
          description: "Review proposal and generate PDF (Phase 10.8).",
          content: (
            <div className="space-y-4">
              <div className="p-4 bg-gray-50 border rounded-lg">
                <div className="flex items-start gap-2 mb-3">
                  <FileText className="h-5 w-5 text-gray-600 mt-0.5" />
                  <div>
                    <div className="font-medium">Proposal Ready</div>
                    <div className="text-sm text-gray-600 mt-1">
                      Review the Proposal tab to see the formatted proposal with markdown preview.
                    </div>
                  </div>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      // Navigate to proposal tab would be handled by parent
                      if (onHighlightTab) {
                        onHighlightTab("proposal");
                      }
                    }}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    View Proposal
                  </Button>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                The Proposal tab shows the markdown preview. Use the "Generate Proposal PDF" button to create a PDF with evidence highlights.
              </p>
            </div>
          ),
        };
    }
  };

  const stepContent = getStepContent();

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl relative">
        <Button
          variant="ghost"
          size="icon"
          className="absolute top-4 right-4"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
        <CardHeader>
          <div className="flex items-center justify-between mb-2">
            <CardTitle>{stepContent.title}</CardTitle>
            <Badge variant="outline">
              Step {currentStep + 1} of {STEP_ORDER.length}
            </Badge>
          </div>
          <CardDescription>{stepContent.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="min-h-[200px]">{stepContent.content}</div>
          <div className="flex items-center justify-between pt-4 border-t">
            <Button
              variant="outline"
              onClick={prevStep}
              disabled={isFirstStep}
            >
              <ChevronLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
            <div className="flex gap-2">
              {STEP_ORDER.map((_, idx) => (
                <div
                  key={idx}
                  className={`h-2 w-2 rounded-full ${
                    idx === currentStep ? "bg-emerald-600" : "bg-gray-300"
                  }`}
                />
              ))}
            </div>
            {isLastStep ? (
              <Button onClick={onClose}>
                Finish
              </Button>
            ) : (
              <Button onClick={nextStep}>
                Next
                <ChevronRight className="h-4 w-4 ml-2" />
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
