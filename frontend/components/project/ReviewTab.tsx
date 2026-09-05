"use client";

import { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { AlertCircle, Loader2, FileText, AlertTriangle, Info, CheckCircle2, RotateCcw, ExternalLink, Shield } from "lucide-react";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { useEvidenceIndex } from "@/lib/useEvidenceIndex";
import { enrichWithSheetTitles } from "@/lib/evidence-normalizer";
import { getTerm, getBadgeVariant, getBadgeLabel } from "@/lib/terminology";
import { Skeleton } from "@/components/ui/skeleton";

interface ReviewTabProps {
  projectId: string;
}

interface RuleRef {
  rule_name: string;
  yaml_file: string;
  match_keywords_used: string[];
}

interface MultiplierApplied {
  name: string;
  factor: number;
}

interface EvidenceRef {
  page_number: number;
  sheet_id?: string | null;
  snippet?: string | null;
}

interface BidLineItemReview {
  line_item_id: string;
  line_item_index: number;
  division: string;
  title: string;
  quantity: number;
  unit: string;
  unit_cost: number;
  total_cost: number;
  rule_refs: RuleRef[];
  multipliers_applied: MultiplierApplied[];
  quantity_source: "explicit_takeoff" | "derived_from_dimensions" | "heuristic" | "recovered" | "allowance" | "unknown";
  evidence_refs: EvidenceRef[];
  flags: string[];
}

interface BidReview {
  project_id: string;
  total_bid: number;
  line_items: BidLineItemReview[];
  recovery_performed: boolean;
  recovery_pages: number[];
  generated_at: string;
}

interface BidProposal {
  clarifications: Array<{
    text: string;
    severity: "info" | "warning" | "critical";
  }>;
}

interface ValidationReport {
  rerun_performed: boolean;
  rerun_notes: string[];
}

export function ReviewTab({ projectId }: ReviewTabProps) {
  const [bidVersion, setBidVersion] = useState<"original" | "normalized">("original"); // Phase 10.11B
  const [bidProposalV2, setBidProposalV2] = useState<any | null>(null); // Phase 10.11B
  const [normalizationReport, setNormalizationReport] = useState<any | null>(null); // Phase 10.11B
  const [bidReview, setBidReview] = useState<BidReview | null>(null);
  const [bidProposal, setBidProposal] = useState<BidProposal | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [constructionSystems, setConstructionSystems] = useState<any | null>(null); // Phase 14.1
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedItemIndex, setSelectedItemIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { getEvidenceForBidItem, documentAnalysis } = useEvidenceIndex(projectId);

  useEffect(() => {
    const loadData = async () => {
      try {
        // Load bid review (primary)
        const review = await api.getArtifact<BidReview>(projectId, "bid_review");
        if (!review) {
          setError("Bid review not available. The project may still be processing.");
          setLoading(false);
          return;
        }
        setBidReview(review);

        // Optionally load bid proposal for clarifications
        const proposal = await api.getArtifact<BidProposal>(projectId, "bid_proposal");
        if (proposal) {
          setBidProposal(proposal);
        }

        // Phase 10.11B: Try to load normalized version
        const proposalV2 = await api.getArtifact<any>(projectId, "bid_proposal_v2");
        if (proposalV2) {
          setBidProposalV2(proposalV2);
          // Also try to load normalization report
          const report = await api.getArtifact<any>(projectId, "quantity_normalization_report");
          if (report) {
            setNormalizationReport(report);
          }
        }

        // Optionally load validation report for recovery info
        const validationReport = await api.getArtifact<ValidationReport>(projectId, "validation_report");
        if (validationReport) {
          setValidationReport(validationReport);
        }

        // Phase 14.1: Load construction systems
        const systems = await api.getArtifact<any>(projectId, "construction_systems");
        if (systems) {
          setConstructionSystems(systems);
        }

        setError(null);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load bid review.");
        }
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId]);

  const handleOpenEvidence = (itemIndex: number) => {
    setSelectedItemIndex(itemIndex);
    setEvidenceDrawerOpen(true);
  };

  const selectedItem = selectedItemIndex !== null && bidReview
    ? bidReview.line_items[selectedItemIndex]
    : null;

  // Use evidence_refs directly from bid_review (it already has the evidence)
  // Normalize to match EvidenceDrawer's expected format and enrich with sheet titles
  const rawEvidence = selectedItem?.evidence_refs && selectedItem.evidence_refs.length > 0
    ? selectedItem.evidence_refs.map((ref) => ({
        page_number: ref.page_number,
        sheet_id: ref.sheet_id || null,
        sheet_title: null, // Will be enriched below
        location_type: null,
        snippet: ref.snippet || null,
        detail_refs: [],
        source: "bid_item" as const,
        bbox: (ref as any).bbox || null,
        bbox_source: (ref as any).bbox_source || "none",
      }))
    : (selectedItemIndex !== null ? getEvidenceForBidItem(selectedItemIndex) : []);
  
  // Enrich with sheet titles if document_analysis is available
  const selectedEvidence = enrichWithSheetTitles(rawEvidence, documentAnalysis);

  if (loading) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-8 w-16" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Skeleton className="h-6 w-48" />
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-full" />
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error && !bidReview) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!bidReview) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>Bid review not available</AlertDescription>
      </Alert>
    );
  }

  // Group clarifications by severity
  const clarificationsBySeverity = {
    critical: bidProposal?.clarifications.filter(c => c.severity === "critical") || [],
    warning: bidProposal?.clarifications.filter(c => c.severity === "warning") || [],
    info: bidProposal?.clarifications.filter(c => c.severity === "info") || [],
  };

  // Phase 1: Extract compliance adjustments from clarifications
  const complianceAdjustments = clarificationsBySeverity.info.filter(
    c => c.text.includes("Compliance adjustment applied:") || 
         c.text.includes("Prevailing wage") || 
         c.text.includes("Performance & Payment Bonds") ||
         c.text.includes("Supplemental Insurance")
  );

  const getFlagBadgeVariant = (flag: string) => {
    return getBadgeVariant(flag);
  };

  const getQuantitySourceBadgeVariant = (source: string) => {
    return getBadgeVariant("", source);
  };

  return (
    <div className="space-y-6">
      {/* Phase 10.11B: Normalization toggle (if v2 exists) */}
      {bidProposalV2 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Bid Version</CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  variant={bidVersion === "original" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setBidVersion("original")}
                >
                  Original
                </Button>
                <Button
                  variant={bidVersion === "normalized" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setBidVersion("normalized")}
                >
                  Normalized
                </Button>
                {bidVersion === "normalized" && normalizationReport && (
                  <Badge variant="secondary" className="ml-2">
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/artifacts/quantity_normalization_report`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 hover:underline"
                    >
                      {normalizationReport.changes?.length || 0} changes
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
        </Card>
      )}
      {/* Recovery Banner */}
      {bidReview.recovery_performed && (
        <Alert className="border-amber-200 bg-amber-50">
          <RotateCcw className="h-4 w-4 text-amber-600" />
          <AlertDescription className="text-amber-900">
            <div className="font-semibold mb-1">🔁 Automatically Verified</div>
            <div className="text-sm">
              Missing items were automatically verified from drawings by re-reading pages: {bidReview.recovery_pages.join(", ")}
            </div>
            {validationReport?.rerun_notes && validationReport.rerun_notes.length > 0 && (
              <div className="text-xs mt-2 space-y-1">
                {validationReport.rerun_notes.map((note, idx) => (
                  <div key={idx}>• {note}</div>
                ))}
              </div>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Phase 1: Compliance Adjustments Summary */}
      {complianceAdjustments.length > 0 && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-blue-600" />
              <CardTitle>Compliance Adjustments Applied</CardTitle>
            </div>
            <CardDescription>
              Government/public project compliance requirements have been automatically applied to this bid
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {complianceAdjustments.map((adj, idx) => {
                // Remove the "Compliance adjustment applied: " prefix for cleaner display
                const cleanText = adj.text.replace(/^Compliance adjustment applied:\s*/i, "");
                return (
                  <Alert key={idx} className="bg-white border-blue-200">
                    <Info className="h-4 w-4 text-blue-600" />
                    <AlertDescription className="text-sm">{cleanText}</AlertDescription>
                  </Alert>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle>Bid Review Summary</CardTitle>
          <CardDescription>
            Total Bid: ${(bidReview.total_bid || bidReview.summary?.total_cost || 0).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-muted-foreground">Line Items</div>
              <div className="text-2xl font-bold">{bidReview.line_items.length}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">With Flags</div>
              <div className="text-2xl font-bold text-amber-600">
                {bidReview.line_items.filter(item => item.flags.length > 0).length}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Auto-Verified</div>
              <div className="text-2xl font-bold text-emerald-600">
                {bidReview.line_items.filter(item => item.flags.includes("recovered_item")).length}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Review Recommended</div>
              <div className="text-2xl font-bold text-amber-600">
                {bidReview.line_items.filter(item => item.flags.includes("heuristic_quantity")).length}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Line Items Review */}
      <div className="space-y-4">
        <h2 className="text-xl font-semibold">Line Item Breakdown</h2>
        <Accordion type="multiple" className="w-full">
          {bidReview.line_items.map((item) => (
            <AccordionItem key={item.line_item_id} value={item.line_item_id}>
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center justify-between w-full pr-4">
                  <div className="flex items-center gap-3">
                    <div>
                      <div className="font-medium text-left">
                        {item.division} — {item.title}
                      </div>
                      <div className="text-sm text-muted-foreground text-left">
                        ${item.total_cost.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.flags.map((flag) => (
                      <Badge
                        key={flag}
                        variant={getFlagBadgeVariant(flag)}
                        className="text-xs"
                      >
                        {getBadgeLabel(flag)}
                      </Badge>
                    ))}
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4 pt-2">
                  {/* Quantity & Cost */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-muted-foreground">Quantity</div>
                      <div className="text-lg font-semibold">
                        {item.quantity.toLocaleString()} {item.unit}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Unit Cost</div>
                      <div className="text-lg font-semibold">
                        ${item.unit_cost.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Total Cost</div>
                      <div className="text-lg font-semibold">
                        ${item.total_cost.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Quantity Source</div>
                      <Badge variant={getQuantitySourceBadgeVariant(item.quantity_source)}>
                        {getTerm(item.quantity_source)}
                      </Badge>
                    </div>
                  </div>

                  <Separator />

                  {/* Multipliers */}
                  {item.multipliers_applied.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Multipliers Applied</h4>
                      <div className="flex flex-wrap gap-2">
                        {item.multipliers_applied.map((mult, idx) => (
                          <Badge key={idx} variant="outline" className="font-mono">
                            {mult.name}: {mult.factor.toFixed(2)}x
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Rule References */}
                  {item.rule_refs.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Cost Rules</h4>
                      {item.rule_refs.map((rule, idx) => (
                        <div key={idx} className="space-y-1 mb-2">
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary">{rule.rule_name}</Badge>
                            <span className="text-xs text-muted-foreground font-mono">
                              {rule.yaml_file}
                            </span>
                          </div>
                          {rule.match_keywords_used.length > 0 && (
                            <div className="text-xs text-muted-foreground">
                              Matched keywords: {rule.match_keywords_used.join(", ")}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <Separator />

                  {/* Evidence */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold">Evidence</h4>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleOpenEvidence(item.line_item_index)}
                      >
                        <FileText className="h-4 w-4 mr-1" />
                        View Evidence
                      </Button>
                    </div>
                    {item.evidence_refs.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {item.evidence_refs.map((ref, idx) => (
                          <Button
                            key={idx}
                            variant="outline"
                            size="sm"
                            className="font-mono"
                            onClick={() => {
                              // Open evidence drawer and navigate to this specific page
                              setSelectedItemIndex(item.line_item_index);
                              setEvidenceDrawerOpen(true);
                              // The EvidenceDrawer will use initialPage prop to jump to this page
                            }}
                          >
                            Page {ref.page_number}
                            {ref.sheet_id && (
                              <Badge variant="secondary" className="ml-2 text-xs">
                                {ref.sheet_id}
                              </Badge>
                            )}
                          </Button>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No evidence references available</p>
                    )}
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>

      {/* Phase 14.1: Construction Systems */}
      {constructionSystems && constructionSystems.systems && constructionSystems.systems.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Construction Systems</h2>
          <Card>
            <CardHeader>
              <CardDescription>
                Line items grouped into construction systems ({constructionSystems.systems.length} systems)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Accordion type="multiple" className="w-full">
                {constructionSystems.systems.map((system: any) => (
                  <AccordionItem key={system.id} value={system.id}>
                    <AccordionTrigger className="hover:no-underline">
                      <div className="flex items-center justify-between w-full pr-4">
                        <div className="flex items-center gap-3">
                          <div>
                            <div className="font-medium text-left">{system.description}</div>
                            <div className="text-sm text-muted-foreground text-left">
                              ${system.cost_summary.total_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">
                            {system.system_type.replace(/_/g, " ")}
                          </Badge>
                          <Badge
                            variant={system.confidence >= 0.8 ? "default" : "secondary"}
                            className="text-xs"
                          >
                            {Math.round(system.confidence * 100)}% confidence
                          </Badge>
                        </div>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4 pt-2">
                        {/* Cost Breakdown */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          <div>
                            <div className="text-sm text-muted-foreground">Material Cost</div>
                            <div className="text-lg font-semibold">
                              ${system.cost_summary.material_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                          <div>
                            <div className="text-sm text-muted-foreground">Labor Cost</div>
                            <div className="text-lg font-semibold">
                              ${system.cost_summary.labor_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                          <div>
                            <div className="text-sm text-muted-foreground">Equipment Cost</div>
                            <div className="text-lg font-semibold">
                              ${system.cost_summary.equipment_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                          <div>
                            <div className="text-sm text-muted-foreground">Total Cost</div>
                            <div className="text-lg font-semibold">
                              ${system.cost_summary.total_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </div>
                          </div>
                        </div>

                        <Separator />

                        {/* Quantities */}
                        <div>
                          <h4 className="text-sm font-semibold mb-2">Quantities</h4>
                          <div className="flex items-center gap-4">
                            <div>
                              <span className="text-sm text-muted-foreground">Primary: </span>
                              <span className="font-semibold">
                                {system.quantities.primary_quantity.toLocaleString()} {system.quantities.primary_unit}
                              </span>
                            </div>
                            {system.quantities.secondary_quantities &&
                              Object.keys(system.quantities.secondary_quantities).length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {Object.entries(system.quantities.secondary_quantities).map(([unit, qty]) => (
                                    <Badge key={unit} variant="outline">
                                      {Number(qty).toLocaleString()} {unit}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                          </div>
                        </div>

                        {/* Zones */}
                        {system.zones && system.zones.length > 0 && (
                          <>
                            <Separator />
                            <div>
                              <h4 className="text-sm font-semibold mb-2">Zones</h4>
                              <div className="flex flex-wrap gap-2">
                                {system.zones.map((zoneId: string) => (
                                  <Badge key={zoneId} variant="secondary">
                                    {zoneId}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </>
                        )}

                        {/* Source Divisions */}
                        {system.source_divisions && system.source_divisions.length > 0 && (
                          <>
                            <Separator />
                            <div>
                              <h4 className="text-sm font-semibold mb-2">CSI Divisions</h4>
                              <div className="flex flex-wrap gap-2">
                                {system.source_divisions.map((div: string) => (
                                  <Badge key={div} variant="outline">
                                    {div}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </>
                        )}

                        {/* Linked Line Items */}
                        {system.base_scope_items && system.base_scope_items.length > 0 && (
                          <>
                            <Separator />
                            <div>
                              <h4 className="text-sm font-semibold mb-2">Linked Line Items</h4>
                              <div className="flex flex-wrap gap-2">
                                {system.base_scope_items.map((itemId: string) => (
                                  <Badge key={itemId} variant="secondary" className="font-mono">
                                    Item {Number(itemId) + 1}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </>
                        )}

                        {/* Subcomponents */}
                        {system.subcomponents && system.subcomponents.length > 0 && (
                          <>
                            <Separator />
                            <div>
                              <h4 className="text-sm font-semibold mb-2">Subcomponents</h4>
                              <div className="space-y-2">
                                {system.subcomponents.map((sub: any, idx: number) => (
                                  <div key={idx} className="flex items-start gap-2">
                                    <Badge variant="outline">{sub.category}</Badge>
                                    <span className="text-sm text-muted-foreground">{sub.description}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </>
                        )}

                        {/* Evidence */}
                        {system.evidence_refs && system.evidence_refs.length > 0 && (
                          <>
                            <Separator />
                            <div>
                              <h4 className="text-sm font-semibold mb-2">Evidence</h4>
                              <div className="flex flex-wrap gap-2">
                                {system.evidence_refs.map((ref: any, idx: number) => (
                                  <Button
                                    key={idx}
                                    variant="outline"
                                    size="sm"
                                    className="font-mono"
                                    onClick={() => {
                                      // Could open evidence drawer if needed
                                    }}
                                  >
                                    Page {ref.page_number}
                                    {ref.sheet_id && (
                                      <Badge variant="secondary" className="ml-2 text-xs">
                                        {ref.sheet_id}
                                      </Badge>
                                    )}
                                  </Button>
                                ))}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Clarifications Center */}
      {(clarificationsBySeverity.critical.length > 0 ||
        clarificationsBySeverity.warning.length > 0 ||
        clarificationsBySeverity.info.length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>Clarifications Center</CardTitle>
            <CardDescription>
              System-generated clarifications and assumptions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Critical */}
            {clarificationsBySeverity.critical.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  Critical ({clarificationsBySeverity.critical.length})
                </h3>
                <div className="space-y-2">
                  {clarificationsBySeverity.critical.map((clar, idx) => (
                    <Alert key={idx} variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{clar.text}</AlertDescription>
                    </Alert>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings */}
            {clarificationsBySeverity.warning.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  Warnings ({clarificationsBySeverity.warning.length})
                </h3>
                <div className="space-y-2">
                  {clarificationsBySeverity.warning.map((clar, idx) => (
                    <Alert key={idx}>
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription>{clar.text}</AlertDescription>
                    </Alert>
                  ))}
                </div>
              </div>
            )}

            {/* Info */}
            {clarificationsBySeverity.info.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <Info className="h-4 w-4 text-blue-500" />
                  Info ({clarificationsBySeverity.info.length})
                </h3>
                <div className="space-y-2">
                  {clarificationsBySeverity.info.map((clar, idx) => (
                    <Alert key={idx}>
                      <Info className="h-4 w-4" />
                      <AlertDescription>{clar.text}</AlertDescription>
                    </Alert>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Evidence Drawer */}
      <EvidenceDrawer
        open={evidenceDrawerOpen}
        onOpenChange={setEvidenceDrawerOpen}
        title={selectedItem ? `${selectedItem.division} — ${selectedItem.title}` : "Evidence"}
        subtitle={selectedItem ? `Line item ${selectedItemIndex !== null ? selectedItemIndex + 1 : ""}` : undefined}
        evidence={selectedEvidence}
        projectId={projectId}
        initialPage={
          selectedItem && selectedItem.evidence_refs.length > 0
            ? selectedItem.evidence_refs[0].page_number
            : selectedEvidence.length > 0
            ? selectedEvidence[0].page_number
            : undefined
        }
        initialEvidenceIndex={0}
      />
    </div>
  );
}

