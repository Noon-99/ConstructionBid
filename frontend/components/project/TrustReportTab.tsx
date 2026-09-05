"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, CheckCircle2, AlertTriangle, FileText, Download, Shield } from "lucide-react";

interface TrustReportTabProps {
  projectId: string;
}

interface TrustReport {
  project_id: string;
  project_name?: string;
  project_type: string;
  run_id: string;
  generated_at: string;
  bid_ready: boolean;
  overall_confidence: number;
  confidence_explanation: string;
  confidence_breakdown: {
    scope_coverage: number;
    quantity_confidence: number;
    evidence_coverage: number;
    geometry_quality: string;
  };
  verified_items: Array<{
    item: string;
    evidence_pages: number[];
    detail_refs: string[];
  }>;
  recovery_applied: boolean;
  recovery_pages: number[];
  review_recommended_items: Array<{
    item: string;
    reason: string;
    quantity_source?: string;
  }>;
  evidence_coverage: {
    bid_value_coverage_pct: number;
    items_with_evidence_pct: number;
    orphan_items_count: number;
    referenced_pages: number[];
    detail_refs: string[];
  };
  geometry_confidence: {
    model_generated: boolean;
    buildings_count: number;
    work_zones_count: number;
    geometry_type: string;
    used_for: string[];
  };
  included_items: string[];
  excluded_items: string[];
  validation_gates_passed: boolean;
  critical_recovery_applied: boolean;
  cache_reuse_enabled: boolean;
  deterministic_run: boolean;
  mode: string;
  run_timestamp: string;
  coverage_declarations?: {
    insurance: {
      general_liability_limit?: string | null;
      general_liability_status: string;
      workers_comp_status: string;
      umbrella_limit?: string | null;
      umbrella_status: string;
      bond_status: string;
      notes?: string | null;
    };
    warranty: {
      workmanship_duration?: string | null;
      workmanship_status: string;
      materials_basis?: string | null;
      materials_status: string;
      notes?: string | null;
    };
    source: string;
    updated_at?: string | null;
  } | null;
}

export function TrustReportTab({ projectId }: TrustReportTabProps) {
  const [trustReport, setTrustReport] = useState<TrustReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadTrustReport = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/trust_report`
        );
        if (!response.ok) {
          throw new Error(`Failed to load trust report: ${response.statusText}`);
        }
        const data = await response.json();
        setTrustReport(data);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to load trust report");
      } finally {
        setLoading(false);
      }
    };

    loadTrustReport();
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
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

  if (!trustReport) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>No trust report data available.</AlertDescription>
      </Alert>
    );
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header - Bid Status */}
      <Card className="border-l-4 border-l-green-500">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <Shield className="h-6 w-6 text-green-600" />
                <CardTitle className="text-2xl">Trust Report</CardTitle>
              </div>
              <CardDescription className="space-y-1">
                <div>
                  <strong>Project:</strong> {trustReport.project_name || projectId}
                </div>
                <div>
                  <strong>Project Type:</strong> {trustReport.project_type}
                </div>
                <div>
                  <strong>Run ID:</strong> {trustReport.run_id}
                </div>
                <div>
                  <strong>Date:</strong> {formatDate(trustReport.run_timestamp)}
                </div>
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                // TODO: Implement PDF export
                window.print();
              }}
            >
              <Download className="h-4 w-4 mr-2" />
              Export PDF
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {trustReport.bid_ready ? (
                <>
                  <div className="h-4 w-4 rounded-full bg-green-500" />
                  <span className="text-lg font-semibold">BID READY ({trustReport.mode.toUpperCase()})</span>
                </>
              ) : (
                <>
                  <div className="h-4 w-4 rounded-full bg-amber-500" />
                  <span className="text-lg font-semibold">REVIEW REQUIRED</span>
                </>
              )}
            </div>
            <div className="flex-1">
              <div className="text-3xl font-bold">{trustReport.overall_confidence.toFixed(0)}%</div>
              <div className="text-sm text-gray-600">Overall Confidence</div>
            </div>
          </div>
          <Alert className="mt-4 bg-green-50 border-green-200">
            <AlertDescription className="text-green-900">
              {trustReport.confidence_explanation}
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="space-y-6">
          {/* Section 1: Bid Confidence Snapshot */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Bid Confidence Snapshot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Scope Coverage</span>
                  <span className="font-semibold">{(trustReport.confidence_breakdown.scope_coverage * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{ width: `${trustReport.confidence_breakdown.scope_coverage * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Quantity Confidence</span>
                  <span className="font-semibold">{(trustReport.confidence_breakdown.quantity_confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{ width: `${trustReport.confidence_breakdown.quantity_confidence * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Evidence Coverage</span>
                  <span className="font-semibold">{(trustReport.confidence_breakdown.evidence_coverage * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{ width: `${trustReport.confidence_breakdown.evidence_coverage * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Geometry Quality</span>
                  <Badge variant="outline">{trustReport.confidence_breakdown.geometry_quality}</Badge>
                </div>
              </div>
              <Alert className="bg-blue-50 border-blue-200">
                <AlertDescription className="text-sm text-blue-900">
                  Confidence score reflects validation, recovery, and evidence coverage — not pricing margin.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          {/* Section 2: What the AI Verified */}
          <Card className="border-l-4 border-l-green-500">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
                What the AI Verified
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-700 mb-4">Automatically Verified from Drawings</p>
              <ul className="space-y-2 mb-4">
                {trustReport.verified_items.slice(0, 5).map((item, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="font-medium">{item.item}</div>
                      {item.evidence_pages.length > 0 && (
                        <div className="text-xs text-gray-500">
                          Pages: {item.evidence_pages.join(", ")}
                          {item.detail_refs.length > 0 && ` | Details: ${item.detail_refs.join(", ")}`}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {trustReport.recovery_applied && (
                <Alert className="bg-green-50 border-green-200">
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  <AlertDescription className="text-sm text-green-900">
                    <strong>Recovery Applied:</strong> Missing scope items were verified by targeted re-reads
                    {trustReport.recovery_pages.length > 0 && ` (Pages: ${trustReport.recovery_pages.join(", ")})`}
                  </AlertDescription>
                </Alert>
              )}
              <p className="text-xs text-gray-500 mt-4 italic">
                No assumptions were made without drawing confirmation.
              </p>
            </CardContent>
          </Card>

          {/* Section 3: Where Human Review is Advised */}
          {trustReport.review_recommended_items.length > 0 && (
            <Card className="border-l-4 border-l-amber-500">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  Review Recommended ({trustReport.review_recommended_items.length} items)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Item</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {trustReport.review_recommended_items.map((item, idx) => (
                      <TableRow key={idx}>
                        <TableCell className="font-medium">{item.item}</TableCell>
                        <TableCell className="text-sm text-gray-600">{item.reason}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Alert className="mt-4 bg-amber-50 border-amber-200">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <AlertDescription className="text-sm text-amber-900">
                    <strong>Why this matters:</strong> These items are valid in scope but unit expressions may differ by contractor practice (LF vs EA).
                  </AlertDescription>
                </Alert>
                <p className="text-xs text-gray-500 mt-2 italic">
                  System flags these intentionally — they are not hidden.
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Section 4: Evidence Coverage */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Evidence Coverage</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="text-3xl font-bold text-green-600">
                  {trustReport.evidence_coverage.bid_value_coverage_pct.toFixed(0)}%
                </div>
                <div className="text-sm text-gray-600">of total bid value linked to drawing evidence</div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-lg font-semibold">{trustReport.evidence_coverage.items_with_evidence_pct.toFixed(0)}%</div>
                  <div className="text-xs text-gray-600">Items with evidence</div>
                </div>
                <div>
                  <div className="text-lg font-semibold">{trustReport.evidence_coverage.orphan_items_count}</div>
                  <div className="text-xs text-gray-600">Orphan items</div>
                </div>
              </div>
              <div>
                <div className="text-sm font-medium mb-1">Referenced Pages:</div>
                <div className="text-sm text-gray-600">
                  {trustReport.evidence_coverage.referenced_pages.length > 0
                    ? trustReport.evidence_coverage.referenced_pages.join(", ")
                    : "None"}
                </div>
              </div>
              {trustReport.evidence_coverage.detail_refs.length > 0 && (
                <div>
                  <div className="text-sm font-medium mb-1">Details Linked:</div>
                  <div className="text-sm text-gray-600">{trustReport.evidence_coverage.detail_refs.join(", ")}</div>
                </div>
              )}
              <Alert className="bg-emerald-50 border-emerald-200">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <AlertDescription className="text-sm text-emerald-900">
                  Every major dollar amount can be traced back to a drawing.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          {/* Section 5: Geometry & 3D Confidence */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Geometry & 3D Confidence</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">3D Model Status:</span>
                {trustReport.geometry_confidence.model_generated ? (
                  <Badge variant="default">Generated</Badge>
                ) : (
                  <Badge variant="secondary">Not Generated</Badge>
                )}
              </div>
              {trustReport.geometry_confidence.model_generated && (
                <>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="font-semibold">{trustReport.geometry_confidence.buildings_count}</div>
                      <div className="text-gray-600">Buildings</div>
                    </div>
                    <div>
                      <div className="font-semibold">{trustReport.geometry_confidence.work_zones_count}</div>
                      <div className="text-gray-600">Work Zones</div>
                    </div>
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">Geometry Type:</div>
                    <div className="text-sm text-gray-600">{trustReport.geometry_confidence.geometry_type}</div>
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">3D is used for:</div>
                    <ul className="text-sm text-gray-600 list-disc list-inside">
                      {trustReport.geometry_confidence.used_for.map((use, idx) => (
                        <li key={idx}>{use}</li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
              <Alert className="bg-blue-50 border-blue-200">
                <AlertDescription className="text-xs text-blue-900">
                  3D is a verification aid — not a construction model.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          {/* Section 6: Includes/Excludes */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">What This Bid Includes / Excludes</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-2 gap-6">
                <div>
                  <h4 className="font-semibold mb-2">Included</h4>
                  <ul className="space-y-1 text-sm">
                    {trustReport.included_items.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4 className="font-semibold mb-2">Not Included</h4>
                  <ul className="space-y-1 text-sm">
                    {trustReport.excluded_items.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <AlertCircle className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 7: Coverage & Warranty (Contractor Declared) */}
          {trustReport.coverage_declarations && (
            <Card className="border-l-4 border-l-blue-500">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Shield className="h-5 w-5 text-blue-600" />
                  Coverage & Warranty (Contractor Declared)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <h4 className="font-semibold mb-3 text-sm">Insurance</h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">General Liability:</span>
                        <Badge variant={trustReport.coverage_declarations.insurance.general_liability_status === "declared" ? "default" : "secondary"}>
                          {trustReport.coverage_declarations.insurance.general_liability_status === "declared" ? "Declared" : "Not Declared"}
                        </Badge>
                      </div>
                      {trustReport.coverage_declarations.insurance.general_liability_limit && (
                        <div className="text-gray-600 ml-4 text-xs">
                          Limit: {trustReport.coverage_declarations.insurance.general_liability_limit}
                        </div>
                      )}
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">Workers Comp:</span>
                        <Badge variant={trustReport.coverage_declarations.insurance.workers_comp_status === "declared" ? "default" : "secondary"}>
                          {trustReport.coverage_declarations.insurance.workers_comp_status === "declared" ? "Declared" : "Not Declared"}
                        </Badge>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">Umbrella:</span>
                        <Badge variant={trustReport.coverage_declarations.insurance.umbrella_status === "declared" ? "default" : "secondary"}>
                          {trustReport.coverage_declarations.insurance.umbrella_status === "declared" ? "Declared" : "Not Declared"}
                        </Badge>
                      </div>
                      {trustReport.coverage_declarations.insurance.umbrella_limit && (
                        <div className="text-gray-600 ml-4 text-xs">
                          Limit: {trustReport.coverage_declarations.insurance.umbrella_limit}
                        </div>
                      )}
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">Bond:</span>
                        <Badge variant={
                          trustReport.coverage_declarations.insurance.bond_status === "available" ? "default" :
                          trustReport.coverage_declarations.insurance.bond_status === "not_available" ? "destructive" : "secondary"
                        }>
                          {trustReport.coverage_declarations.insurance.bond_status === "available" ? "Available" :
                           trustReport.coverage_declarations.insurance.bond_status === "not_available" ? "Not Available" : "Not Declared"}
                        </Badge>
                      </div>
                    </div>
                  </div>
                  <div>
                    <h4 className="font-semibold mb-3 text-sm">Warranty</h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">Workmanship:</span>
                        <Badge variant={trustReport.coverage_declarations.warranty.workmanship_status === "declared" ? "default" : "secondary"}>
                          {trustReport.coverage_declarations.warranty.workmanship_status === "declared" ? "Declared" : "Not Declared"}
                        </Badge>
                      </div>
                      {trustReport.coverage_declarations.warranty.workmanship_duration && (
                        <div className="text-gray-600 ml-4 text-xs">
                          Duration: {trustReport.coverage_declarations.warranty.workmanship_duration}
                        </div>
                      )}
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700">Materials:</span>
                        <Badge variant={trustReport.coverage_declarations.warranty.materials_status === "declared" ? "default" : "secondary"}>
                          {trustReport.coverage_declarations.warranty.materials_status === "declared" ? "Declared" : "Not Declared"}
                        </Badge>
                      </div>
                      {trustReport.coverage_declarations.warranty.materials_basis && (
                        <div className="text-gray-600 ml-4 text-xs">
                          Basis: {trustReport.coverage_declarations.warranty.materials_basis}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <Alert className="mt-4 bg-blue-50 border-blue-200">
                  <Shield className="h-4 w-4 text-blue-600" />
                  <AlertDescription className="text-sm text-blue-900">
                    <strong>Contractor Declared:</strong> This information is contractor-provided and not verified from drawings.
                  </AlertDescription>
                </Alert>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Section 8: System Integrity (Footer) */}
      <Card className="bg-gray-50">
        <CardHeader>
          <CardTitle className="text-lg">System Integrity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="font-medium">Validation Gates</div>
              <Badge variant={trustReport.validation_gates_passed ? "default" : "destructive"}>
                {trustReport.validation_gates_passed ? "Passed" : "Failed"}
              </Badge>
            </div>
            <div>
              <div className="font-medium">Critical Recovery</div>
              <Badge variant={trustReport.critical_recovery_applied ? "secondary" : "outline"}>
                {trustReport.critical_recovery_applied ? "Applied" : "Not Needed"}
              </Badge>
            </div>
            <div>
              <div className="font-medium">Cache Reuse</div>
              <Badge variant={trustReport.cache_reuse_enabled ? "default" : "outline"}>
                {trustReport.cache_reuse_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <div>
              <div className="font-medium">Deterministic Run</div>
              <Badge variant={trustReport.deterministic_run ? "default" : "outline"}>
                {trustReport.deterministic_run ? "Yes" : "No"}
              </Badge>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t text-xs text-gray-500">
            <div><strong>Generated By:</strong> Construction Bid AI</div>
            <div><strong>Mode:</strong> {trustReport.mode.toUpperCase()} Estimate</div>
            <div><strong>Valid As Of:</strong> {formatDate(trustReport.run_timestamp)}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

