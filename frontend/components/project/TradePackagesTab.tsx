"use client";

import { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2, Download, FileText, ExternalLink, AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import type { EvidenceRef } from "@/lib/evidence-normalizer";

interface TradePackage {
  trade_id: string;
  trade_name: string;
  divisions: string[];
  total_cost: number;
  line_items: Array<{
    line_item_index: number;
    description: string;
    division: string;
    quantity: number | null;
    unit: string | null;
    unit_cost: number | null;
    total_cost: number;
    basis: string;
  }>;
  inclusions: string[];
  exclusions: string[];
  assumptions: string[];
  evidence_refs: Array<{
    page_number: number;
    sheet_id?: string | null;
    evidence_snippet?: string;
    snippet?: string;
    location_type?: string | null;
    bbox?: { x0: number; y0: number; x1: number; y1: number } | null;
    bbox_source?: string | null;
  }>;
  detail_refs: string[];
  generated_at: string;
}

interface TradePackagesExport {
  project_id: string;
  profile_id: string | null;
  generated_at: string;
  packages: TradePackage[];
}

interface TradePackagesTabProps {
  projectId: string;
}

export function TradePackagesTab({ projectId }: TradePackagesTabProps) {
  const [tradePackages, setTradePackages] = useState<TradePackagesExport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTrades, setExpandedTrades] = useState<Set<string>>(new Set());
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRef[]>([]);
  const [selectedEvidenceTitle, setSelectedEvidenceTitle] = useState("");
  const [exportingPdf, setExportingPdf] = useState<Set<string>>(new Set());

  useEffect(() => {
    const loadTradePackages = async () => {
      try {
        const data = await api.getArtifact<TradePackagesExport>(projectId, "trade_packages");
        setTradePackages(data);
        setError(null);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setError("Trade packages not available. The project may still be processing.");
        } else {
          setError("Failed to load trade packages.");
        }
      } finally {
        setLoading(false);
      }
    };

    loadTradePackages();
  }, [projectId]);

  const toggleTrade = (tradeId: string) => {
    const newExpanded = new Set(expandedTrades);
    if (newExpanded.has(tradeId)) {
      newExpanded.delete(tradeId);
    } else {
      newExpanded.add(tradeId);
    }
    setExpandedTrades(newExpanded);
  };

  const convertEvidenceRef = (ref: TradePackage["evidence_refs"][0]): EvidenceRef => {
    const evidenceRef: EvidenceRef = {
      page_number: ref.page_number,
    };
    evidenceRef.snippet = ref.evidence_snippet || ref.snippet || null;
    if (ref.bbox) evidenceRef.bbox = ref.bbox;
    if (ref.bbox_source) evidenceRef.bbox_source = ref.bbox_source as any;
    if (ref.sheet_id !== undefined) evidenceRef.sheet_id = ref.sheet_id;
    if (ref.location_type !== undefined) evidenceRef.location_type = ref.location_type;
    return evidenceRef;
  };

  const handleEvidenceClick = (evidenceRefs: TradePackage["evidence_refs"], title: string) => {
    setSelectedEvidence(evidenceRefs.map(convertEvidenceRef));
    setSelectedEvidenceTitle(title);
    setEvidenceDrawerOpen(true);
  };

  const handleExportPdf = async (tradeId: string, tradeName: string) => {
    setExportingPdf((prev) => new Set(prev).add(tradeId));
    try {
      // Generate trade package PDF
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/trade-packages/${tradeId}/pdf`,
        {
          method: "POST",
        }
      );
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${tradeName.replace(/\s+/g, "_")}_Package_${projectId}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } else {
        alert("Failed to generate PDF. Please try again.");
      }
    } catch (err) {
      console.error("PDF export error:", err);
      alert("Failed to generate PDF. Please try again.");
    } finally {
      setExportingPdf((prev) => {
        const next = new Set(prev);
        next.delete(tradeId);
        return next;
      });
    }
  };

  const handleExportJson = (tradePackage: TradePackage, tradeName: string) => {
    const blob = new Blob([JSON.stringify(tradePackage, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tradeName.replace(/\s+/g, "_")}_Package_${projectId}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!tradePackages || tradePackages.packages.length === 0) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>No trade packages available for this project.</AlertDescription>
      </Alert>
    );
  }

  // Calculate total across all packages
  const grandTotal = tradePackages.packages.reduce((sum, pkg) => sum + pkg.total_cost, 0);

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle>Trade Packages / Subcontractor Breakdown</CardTitle>
          <CardDescription>
            {tradePackages.packages.length} trade package{tradePackages.packages.length !== 1 ? "s" : ""} generated
            {tradePackages.profile_id && (
              <>
                {" • "}
                <span className="font-medium">Profile:</span> {tradePackages.profile_id}
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between pt-2 border-t">
            <span className="text-sm font-medium text-gray-600">Total Package Value:</span>
            <span className="text-2xl font-bold text-gray-900">
              ${grandTotal.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Trade Packages List */}
      <div className="space-y-4">
        {tradePackages.packages.map((pkg) => {
          const isExpanded = expandedTrades.has(pkg.trade_id);
          return (
            <Card key={pkg.trade_id} className="overflow-hidden border-gray-200">
              <CardHeader
                className="cursor-pointer hover:bg-gray-50/50 transition-colors pb-3"
                onClick={() => toggleTrade(pkg.trade_id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-wrap">
                    {isExpanded ? (
                      <ChevronDown className="h-5 w-5 text-gray-500 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-gray-500 flex-shrink-0" />
                    )}
                    <CardTitle className="text-lg font-semibold">{pkg.trade_name}</CardTitle>
                    <Badge variant="secondary" className="text-xs">
                      {pkg.line_items.length} {pkg.line_items.length === 1 ? "item" : "items"}
                    </Badge>
                    {pkg.divisions.length > 0 && (
                      <Badge variant="outline" className="text-xs">
                        {pkg.divisions[0].split(" ")[0]}{" "}
                        {pkg.divisions.length > 1 && `+${pkg.divisions.length - 1}`}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold text-gray-900">
                      ${pkg.total_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </div>
                </div>
              </CardHeader>

              {isExpanded && (
                <CardContent className="space-y-6 pt-4 border-t bg-gray-50/30">
                  {/* Export buttons */}
                  <div className="flex gap-2 justify-end pb-4">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExportJson(pkg, pkg.trade_name);
                      }}
                    >
                      <FileText className="h-4 w-4 mr-2" />
                      Export JSON
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExportPdf(pkg.trade_id, pkg.trade_name);
                      }}
                      disabled={exportingPdf.has(pkg.trade_id)}
                    >
                      {exportingPdf.has(pkg.trade_id) ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Generating PDF...
                        </>
                      ) : (
                        <>
                          <Download className="h-4 w-4 mr-2" />
                          Export PDF
                        </>
                      )}
                    </Button>
                  </div>

                  {/* Line items table */}
                  {pkg.line_items.length > 0 && (
                    <div>
                      <h3 className="text-base font-semibold mb-3 text-gray-900">Line Items</h3>
                      <div className="overflow-x-auto rounded-md border border-gray-200 bg-white">
                        <Table>
                          <TableHeader>
                            <TableRow className="bg-gray-50">
                              <TableHead className="font-semibold">Description</TableHead>
                              <TableHead className="text-right font-semibold">Quantity</TableHead>
                              <TableHead className="text-right font-semibold">Unit</TableHead>
                              <TableHead className="text-right font-semibold">Unit Cost</TableHead>
                              <TableHead className="text-right font-semibold">Total</TableHead>
                              <TableHead className="font-semibold">Basis</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {pkg.line_items.map((item, idx) => (
                              <TableRow key={idx} className="hover:bg-gray-50/50">
                                <TableCell className="font-medium">{item.description}</TableCell>
                                <TableCell className="text-right text-gray-700">
                                  {item.quantity !== null
                                    ? item.quantity.toLocaleString(undefined, {
                                        maximumFractionDigits: 2,
                                      })
                                    : "-"}
                                </TableCell>
                                <TableCell className="text-right text-gray-600">{item.unit || "-"}</TableCell>
                                <TableCell className="text-right text-gray-700">
                                  {item.unit_cost !== null
                                    ? `$${item.unit_cost.toLocaleString(undefined, {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                      })}`
                                    : "-"}
                                </TableCell>
                                <TableCell className="text-right font-semibold text-gray-900">
                                  ${item.total_cost.toLocaleString(undefined, {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </TableCell>
                                <TableCell className="text-sm text-gray-600">{item.basis}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  )}

                  {/* Evidence references */}
                  {pkg.evidence_refs.length > 0 && (
                    <div className="bg-white rounded-md border border-gray-200 p-4">
                      <h3 className="text-base font-semibold mb-3 text-gray-900">Evidence References</h3>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleEvidenceClick(pkg.evidence_refs, pkg.trade_name)}
                      >
                        <ExternalLink className="h-4 w-4 mr-2" />
                        View All Evidence ({pkg.evidence_refs.length} reference{pkg.evidence_refs.length !== 1 ? "s" : ""})
                      </Button>
                    </div>
                  )}

                  {/* Detail references */}
                  {pkg.detail_refs.length > 0 && (
                    <div className="bg-white rounded-md border border-gray-200 p-4">
                      <h3 className="text-base font-semibold mb-3 text-gray-900">Detail References</h3>
                      <div className="flex gap-2 flex-wrap">
                        {pkg.detail_refs.map((ref, idx) => (
                          <Badge key={idx} variant="outline" className="font-mono text-xs">
                            {ref}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Inclusions, Exclusions, Assumptions in grid */}
                  {(pkg.inclusions.length > 0 || pkg.exclusions.length > 0 || pkg.assumptions.length > 0) && (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Inclusions */}
                      {pkg.inclusions.length > 0 && (
                        <div className="bg-white rounded-md border border-gray-200 p-4">
                          <h3 className="text-base font-semibold mb-3 text-gray-900">Inclusions</h3>
                          <ul className="list-disc list-inside space-y-1.5 text-sm text-gray-700">
                            {pkg.inclusions.map((inclusion, idx) => (
                              <li key={idx} className="leading-relaxed">{inclusion}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Exclusions */}
                      {pkg.exclusions.length > 0 && (
                        <div className="bg-white rounded-md border border-gray-200 p-4">
                          <h3 className="text-base font-semibold mb-3 text-gray-900">Exclusions</h3>
                          <ul className="list-disc list-inside space-y-1.5 text-sm text-gray-700">
                            {pkg.exclusions.map((exclusion, idx) => (
                              <li key={idx} className="leading-relaxed">{exclusion}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Assumptions */}
                      {pkg.assumptions.length > 0 && (
                        <div className="bg-white rounded-md border border-gray-200 p-4">
                          <h3 className="text-base font-semibold mb-3 text-gray-900">Assumptions</h3>
                          <ul className="list-disc list-inside space-y-1.5 text-sm text-gray-700">
                            {pkg.assumptions.map((assumption, idx) => (
                              <li key={idx} className="leading-relaxed">{assumption}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>

      <EvidenceDrawer
        open={evidenceDrawerOpen}
        onOpenChange={setEvidenceDrawerOpen}
        evidence={selectedEvidence}
        projectId={projectId}
        title={selectedEvidenceTitle}
      />
    </div>
  );
}

