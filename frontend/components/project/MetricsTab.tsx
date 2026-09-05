"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2, TrendingUp, Clock, DollarSign, CheckCircle2, AlertTriangle, FileText, Zap, Activity } from "lucide-react";

interface MetricsTabProps {
  projectId: string;
}

interface StageMetrics {
  stage_name: string;
  pages_sent?: number;
  tokens_prompt?: number;
  tokens_completion?: number;
  tokens_total?: number;
  latency_seconds?: number;
  cost_estimate_usd?: number;
}

interface Metrics {
  project_id: string;
  created_at?: string;
  stage_metrics?: StageMetrics[];
  total_pages_sent_stage1?: number;
  total_pages_sent_stage2?: number;
  total_pages_sent_recovery?: number;
  total_tokens?: number;
  total_cost_estimate_usd?: number;
  total_latency_seconds?: number;
    critical_coverage_score?: number;
    dimension_confidence?: number;
    validation_score?: number;
  cache_hits_total?: number;
  cache_misses_total?: number;
  cache_hits_by_stage?: Record<string, number>;
  cache_misses_by_stage?: Record<string, number>;
  cache_hit_rate?: number;
  throttle_wait_ms_total?: number;
  throttle_wait_ms_by_stage?: Record<string, number>;
  openai_calls_total?: number;
  openai_calls_by_stage?: Record<string, number>;
}

interface ValidationReport {
  project_id: string;
  passed?: boolean;
  score?: number;
  issues?: Array<{
    code: string;
    severity: string;
    message: string;
  }>;
  missing_critical_items?: string[];
}

interface BidReview {
  project_id: string;
  total_bid?: number;
  line_items?: Array<{
    line_item_index: number;
    flags?: string[];
    evidence_refs?: Array<{ page_number: number }>;
    detail_refs?: string[];
    quantity_source?: string;
    total_cost?: number;
  }>;
}

interface BidProposal {
  project_id: string;
  line_items?: Array<{
    evidence_refs?: Array<{ page_number: number }>;
    detail_refs?: string[];
    quantity_source?: string;
  }>;
}

interface DocumentAnalysis {
  project_id: string;
  key_dimensions?: {
    confidence?: number;
  };
  critical_expected_items?: Array<{
    item: string;
    found: boolean;
  }>;
}

// Stage name mappings for display
const STAGE_NAMES: Record<string, string> = {
  stage_0_5_page_indexing: "Stage 0.5: Page Indexing",
  stage_1_document_analysis: "Stage 1: Document Analysis",
  stage_1_5_typology_resolution: "Stage 1.5: Typology Resolution",
  stage_2_adaptive_extraction: "Stage 2: Extraction",
  stage_2_5a_dimension_authority: "Stage 2.5a: Dimension Authority",
  stage_2_5_validation_gates: "Stage 2.5: Recovery",
  stage_3_validation: "Stage 3: Validation",
  stage_3_model_generation: "Stage 3: 3D Model",
  stage_4_costing: "Stage 4: Costing",
};

export function MetricsTab({ projectId }: MetricsTabProps) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [bidReview, setBidReview] = useState<BidReview | null>(null);
  const [bidProposal, setBidProposal] = useState<BidProposal | null>(null);
  const [documentAnalysis, setDocumentAnalysis] = useState<DocumentAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        // Load all artifacts in parallel
        const [metricsData, validationData, bidReviewData, bidProposalData, documentAnalysisData] = await Promise.all([
          api.getArtifact<Metrics>(projectId, "metrics").catch(() => null),
          api.getArtifact<ValidationReport>(projectId, "validation_report").catch(() => null),
          api.getArtifact<BidReview>(projectId, "bid_review").catch(() => null),
          api.getArtifact<BidProposal>(projectId, "bid_proposal").catch(() => null),
          api.getArtifact<DocumentAnalysis>(projectId, "document_analysis").catch(() => null),
        ]);

        setMetrics(metricsData);
        setValidationReport(validationData);
        setBidReview(bidReviewData);
        setBidProposal(bidProposalData);
        setDocumentAnalysis(documentAnalysisData);
        setError(null);
      } catch (err) {
        setError("Failed to load metrics data.");
      } finally {
        setLoading(false);
      }
    };

    loadData();
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
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!metrics) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>No metrics data available. The project may still be processing.</AlertDescription>
      </Alert>
    );
  }

  // Calculate evidence coverage metrics
  const lineItems = bidReview?.line_items || bidProposal?.line_items || [];
  const itemsWithEvidence = lineItems.filter(item => item.evidence_refs && item.evidence_refs.length > 0).length;
  const itemsWithDetailRefs = lineItems.filter(item => item.detail_refs && item.detail_refs.length > 0).length;
  const heuristicItems = lineItems.filter(item => item.quantity_source === "heuristic" || item.quantity_source === "unknown").length;
  const orphanItems = lineItems.filter(item => (!item.evidence_refs || item.evidence_refs.length === 0) && (!item.detail_refs || item.detail_refs.length === 0)).length;
  
  const evidenceCoverage = lineItems.length > 0 ? (itemsWithEvidence / lineItems.length) * 100 : 0;
  const detailCoverage = lineItems.length > 0 ? (itemsWithDetailRefs / lineItems.length) * 100 : 0;
  
  // Calculate total bid value with evidence (from bidReview if available)
  const totalBidValue = bidReview?.total_bid || 0;
  const itemsWithEvidenceValue = bidReview?.line_items?.filter(item => 
    item.evidence_refs && item.evidence_refs.length > 0
  ).reduce((sum, item) => sum + (item.total_cost || 0), 0) || 0;
  const evidenceValueCoverage = totalBidValue > 0 ? (itemsWithEvidenceValue / totalBidValue) * 100 : 0;

  // Get unique pages referenced
  const allPages = new Set<number>();
  lineItems.forEach(item => {
    item.evidence_refs?.forEach(ref => {
      if (ref.page_number) allPages.add(ref.page_number);
    });
  });

  // Calculate recovery status
  const recoveryTriggered = (metrics.total_pages_sent_recovery || 0) > 0;
  const criticalItemsMissing = validationReport?.missing_critical_items?.length || 0;
  const criticalItemsFound = documentAnalysis?.critical_expected_items?.filter(item => item.found).length || 0;
  const criticalItemsTotal = documentAnalysis?.critical_expected_items?.length || 0;

  return (
    <div className="space-y-6">
      {/* Section 1: Pipeline Performance */}
          <Card>
            <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Pipeline Performance
              </CardTitle>
          <CardDescription>
            Processing time, stages, and scale indicators
          </CardDescription>
            </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Total Processing Time</div>
              <div className="text-2xl font-bold">
                {metrics.total_latency_seconds ? `${metrics.total_latency_seconds.toFixed(2)}s` : "—"}
                </div>
                </div>
            <div>
              <div className="text-sm text-gray-600">Pages Processed</div>
              <div className="text-2xl font-bold">
                {(metrics.total_pages_sent_stage1 || 0) + (metrics.total_pages_sent_stage2 || 0)}
                </div>
                </div>
            <div>
              <div className="text-sm text-gray-600">Recovery Triggered</div>
              <div className="text-2xl font-bold">
                {recoveryTriggered ? (
                  <Badge variant="secondary">Yes</Badge>
                ) : (
                  <Badge variant="outline">No</Badge>
                )}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Recovery Pages</div>
              <div className="text-2xl font-bold">{metrics.total_pages_sent_recovery || 0}</div>
            </div>
          </div>

          {/* Stage Performance Table */}
          {metrics.stage_metrics && metrics.stage_metrics.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Time per Stage</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                    <TableHead className="text-right">Pages</TableHead>
                    <TableHead className="text-right">AI Calls</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metrics.stage_metrics.map((stage) => {
                    const stageDisplayName = STAGE_NAMES[stage.stage_name] || stage.stage_name;
                    const aiCalls = metrics.openai_calls_by_stage?.[stage.stage_name] || 0;
                    return (
                      <TableRow key={stage.stage_name}>
                        <TableCell className="font-medium">{stageDisplayName}</TableCell>
                        <TableCell className="text-right">
                          {stage.latency_seconds ? `${stage.latency_seconds.toFixed(2)}s` : "—"}
                        </TableCell>
                        <TableCell className="text-right">{stage.pages_sent || 0}</TableCell>
                        <TableCell className="text-right">{aiCalls || "—"}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
            </CardContent>
          </Card>

      {/* Section 2: AI Usage & Cost Transparency */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            AI Usage & Cost Transparency
          </CardTitle>
          <CardDescription>
            OpenAI API calls, caching, and estimated costs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Total AI Calls</div>
              <div className="text-2xl font-bold">{metrics.openai_calls_total || 0}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Cache Hit Rate</div>
              <div className="text-2xl font-bold">
                {metrics.cache_hit_rate ? `${metrics.cache_hit_rate.toFixed(1)}%` : "—"}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Cache Hits</div>
              <div className="text-lg font-semibold">{metrics.cache_hits_total || 0}</div>
              <div className="text-xs text-gray-500">{metrics.cache_misses_total || 0} misses</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Estimated Cost</div>
              <div className="text-2xl font-bold">
                {metrics.total_cost_estimate_usd ? `$${metrics.total_cost_estimate_usd.toFixed(4)}` : "—"}
              </div>
            </div>
          </div>

          {/* Cache Performance Message */}
          {metrics.cache_hit_rate !== undefined && (
            <Alert>
              <TrendingUp className="h-4 w-4" />
              <AlertDescription>
                This project was processed with {metrics.cache_hit_rate.toFixed(0)}% cache reuse
                {metrics.throttle_wait_ms_total === 0 || !metrics.throttle_wait_ms_total 
                  ? " and no rate-limit stalls." 
                  : ` with ${(metrics.throttle_wait_ms_total / 1000).toFixed(1)}s throttle wait time.`}
              </AlertDescription>
            </Alert>
          )}

          {/* AI Calls by Stage */}
          {metrics.openai_calls_by_stage && Object.keys(metrics.openai_calls_by_stage).length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">AI Calls by Stage</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead className="text-right">Calls</TableHead>
                    <TableHead className="text-right">Cache Hits</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(metrics.openai_calls_by_stage).map(([stageName, calls]) => {
                    const stageMetric = metrics.stage_metrics?.find(s => s.stage_name === stageName);
                    const stageDisplayName = STAGE_NAMES[stageName] || stageName;
                    const cacheHits = metrics.cache_hits_by_stage?.[stageName] || 0;
                    return (
                      <TableRow key={stageName}>
                        <TableCell className="font-medium">{stageDisplayName}</TableCell>
                        <TableCell className="text-right">{calls}</TableCell>
                        <TableCell className="text-right">{cacheHits}</TableCell>
                        <TableCell className="text-right">
                          {stageMetric?.cost_estimate_usd ? `$${stageMetric.cost_estimate_usd.toFixed(4)}` : "—"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 3: Data Quality & Confidence Indicators */}
          <Card>
            <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5" />
            Data Quality & Confidence Indicators
          </CardTitle>
          <CardDescription>
            Validation scores, recovery status, and inference flags
          </CardDescription>
            </CardHeader>
        <CardContent className="space-y-4">
          {/* Quality Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Validation Score</div>
              <div className="text-2xl font-bold">
                {validationReport?.score !== undefined 
                  ? `${(validationReport.score * 100).toFixed(0)}%`
                  : metrics.validation_score !== undefined
                  ? `${(metrics.validation_score * 100).toFixed(0)}%`
                  : "—"}
                  </div>
              <div className="text-xs text-gray-500">
                {validationReport?.passed !== undefined && (
                  validationReport.passed ? (
                    <Badge variant="default" className="mt-1">Passed</Badge>
                  ) : (
                    <Badge variant="destructive" className="mt-1">Failed</Badge>
                  )
                )}
              </div>
                  </div>
            <div>
              <div className="text-sm text-gray-600">Critical-5 Recovery</div>
              <div className="text-2xl font-bold">
                {criticalItemsTotal > 0 ? (
                  <>
                    {criticalItemsFound}/{criticalItemsTotal}
                  </>
                ) : "—"}
                  </div>
              <div className="text-xs text-gray-500">
                {criticalItemsMissing > 0 && (
                  <Badge variant="secondary" className="mt-1">{criticalItemsMissing} missing</Badge>
                )}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Dimension Confidence</div>
              <div className="text-2xl font-bold">
                {documentAnalysis?.key_dimensions?.confidence !== undefined
                  ? `${(documentAnalysis.key_dimensions.confidence * 100).toFixed(0)}%`
                  : metrics.dimension_confidence !== undefined
                  ? `${(metrics.dimension_confidence * 100).toFixed(0)}%`
                  : "—"}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Heuristic Usage</div>
              <div className="text-2xl font-bold">{heuristicItems}</div>
              <div className="text-xs text-gray-500">items inferred</div>
            </div>
          </div>

          {/* Geometry Quality */}
          <div>
            <h3 className="text-sm font-semibold mb-2">Quality Indicators</h3>
            <div className="space-y-2">
              {metrics.critical_coverage_score !== undefined && (
                <div className="flex justify-between items-center">
                  <span className="text-sm">Critical Coverage Score</span>
                  <Badge variant={metrics.critical_coverage_score >= 0.8 ? "default" : "secondary"}>
                    {(metrics.critical_coverage_score * 100).toFixed(0)}%
                  </Badge>
                </div>
              )}
              {heuristicItems > 0 && (
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    {heuristicItems} line item{heuristicItems !== 1 ? "s" : ""} {heuristicItems === 1 ? "has" : "have"} inferred quantities and may require human review.
                  </AlertDescription>
                </Alert>
              )}
              {criticalItemsMissing > 0 && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {criticalItemsMissing} critical item{criticalItemsMissing !== 1 ? "s" : ""} {criticalItemsMissing === 1 ? "was" : "were"} not found during initial extraction.
                  </AlertDescription>
                </Alert>
              )}
            </div>
              </div>
            </CardContent>
          </Card>

      {/* Section 4: Evidence Coverage Metrics */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Evidence Coverage Metrics
            </CardTitle>
          <CardDescription>
            Traceability and drawing linkage statistics
          </CardDescription>
          </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Items with Evidence</div>
              <div className="text-2xl font-bold">{evidenceCoverage.toFixed(0)}%</div>
              <div className="text-xs text-gray-500">{itemsWithEvidence}/{lineItems.length} items</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Bid Value Covered</div>
              <div className="text-2xl font-bold">{evidenceValueCoverage.toFixed(0)}%</div>
              <div className="text-xs text-gray-500">
                ${itemsWithEvidenceValue.toLocaleString(undefined, { maximumFractionDigits: 0 })} / ${totalBidValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Detail References</div>
              <div className="text-2xl font-bold">{detailCoverage.toFixed(0)}%</div>
              <div className="text-xs text-gray-500">{itemsWithDetailRefs}/{lineItems.length} items</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Pages Referenced</div>
              <div className="text-2xl font-bold">{allPages.size}</div>
              <div className="text-xs text-gray-500">unique pages</div>
            </div>
          </div>

          {/* Key Message */}
          {evidenceValueCoverage > 0 && (
            <Alert className="bg-emerald-50 border-emerald-200">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <AlertDescription className="text-emerald-900">
                <strong>{evidenceValueCoverage.toFixed(0)}% of bid value</strong> is backed by drawing evidence.
              </AlertDescription>
            </Alert>
          )}

          {/* Coverage Details */}
          <div>
            <h3 className="text-sm font-semibold mb-2">Coverage Breakdown</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead className="text-right">Count</TableHead>
                  <TableHead className="text-right">Percentage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>Items with evidence references</TableCell>
                  <TableCell className="text-right">{itemsWithEvidence}</TableCell>
                  <TableCell className="text-right">{evidenceCoverage.toFixed(1)}%</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Items with detail references</TableCell>
                  <TableCell className="text-right">{itemsWithDetailRefs}</TableCell>
                  <TableCell className="text-right">{detailCoverage.toFixed(1)}%</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Items requiring inference (heuristic/unknown)</TableCell>
                  <TableCell className="text-right">{heuristicItems}</TableCell>
                    <TableCell className="text-right">
                    {lineItems.length > 0 ? ((heuristicItems / lineItems.length) * 100).toFixed(1) : "0.0"}%
                    </TableCell>
                </TableRow>
                {orphanItems > 0 && (
                  <TableRow>
                    <TableCell className="text-amber-600">Orphan items (no evidence or detail refs)</TableCell>
                    <TableCell className="text-right text-amber-600">{orphanItems}</TableCell>
                    <TableCell className="text-right text-amber-600">
                      {lineItems.length > 0 ? ((orphanItems / lineItems.length) * 100).toFixed(1) : "0.0"}%
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          </CardContent>
        </Card>
    </div>
  );
}
