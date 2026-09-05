"use client";

import { useState, useEffect, useMemo } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, FileText, Sparkles, Download, ExternalLink } from "lucide-react";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { useEvidenceIndex } from "@/lib/useEvidenceIndex";
import { enrichWithSheetTitles, type EvidenceRef } from "@/lib/evidence-normalizer";
import { getTerm } from "@/lib/terminology";
import { Skeleton } from "@/components/ui/skeleton";

interface BidTabProps {
  projectId: string;
}

interface BidReviewEvidenceRef {
  page_number?: number | null;
  sheet_id?: string | null;
  snippet?: string | null;
  bbox?: { x0: number; y0: number; x1: number; y1: number } | null;
  bbox_source?: string | null;
}

interface BidReviewLineItem {
  line_item_index: number;
  title?: string;
  evidence_refs?: BidReviewEvidenceRef[];
}

interface BidReview {
  line_items?: BidReviewLineItem[];
}

interface ExtractionResult {
  scope_of_work?: Array<{
    item: string;
    description?: string | null;
    page_number?: number | null;
    evidence_snippet?: string | null;
  }>;
  material_specifications?: Array<{
    material_name: string;
    page_number?: number | null;
    evidence_snippet?: string | null;
  }>;
  quantity_takeoff?: Array<{
    item: string;
    page_number?: number | null;
    evidence_snippet?: string | null;
  }>;
  room_program?: {
    rooms?: Array<{
      room_name: string;
      page_number?: number | null;
      evidence_snippet?: string | null;
    }>;
  };
}

const normalizeKey = (value?: string | null): string =>
  (value ?? "").trim().toLowerCase();

const createExtractionEvidenceRef = (
  pageNumber?: number | null,
  snippet?: string | null,
  locationType?: string | null,
): EvidenceRef | null => {
  const trimmedSnippet = snippet?.trim();
  const page = typeof pageNumber === "number" && Number.isFinite(pageNumber) ? pageNumber : 0;

  if ((page <= 0 || Number.isNaN(page)) && (!trimmedSnippet || trimmedSnippet.length === 0)) {
    return null;
  }

  return {
    page_number: page,
    sheet_id: null,
    sheet_title: null,
    location_type: locationType ?? null,
    snippet: trimmedSnippet && trimmedSnippet.length > 0 ? trimmedSnippet : null,
    detail_refs: [],
    source: "extraction",
    bbox: null,
    bbox_source: "none",
  };
};

const buildExtractionEvidenceMap = (
  bid: BidProposal | null,
  extraction: ExtractionResult | null,
): Record<number, EvidenceRef[]> => {
  const map: Record<number, EvidenceRef[]> = {};
  if (!bid || !extraction) {
    return map;
  }

  const lookup = new Map<string, EvidenceRef[]>();

  const pushRef = (key: string, ref: EvidenceRef | null) => {
    if (!key || !ref) return;
    const existing = lookup.get(key);
    if (existing) {
      const duplicate = existing.some(
        (existingRef) =>
          existingRef.page_number === ref.page_number &&
          (existingRef.snippet || "") === (ref.snippet || ""),
      );
      if (!duplicate) {
        existing.push(ref);
      }
    } else {
      lookup.set(key, [ref]);
    }
  };

  extraction.scope_of_work?.forEach((item) => {
    const snippet = item.evidence_snippet || item.description || item.item;
    const ref = createExtractionEvidenceRef(item.page_number, snippet, "scope_of_work");
    pushRef(normalizeKey(item.item), ref);
    pushRef(normalizeKey(item.description), ref);
  });

  extraction.material_specifications?.forEach((item) => {
    const snippet = item.evidence_snippet || item.material_name;
    const ref = createExtractionEvidenceRef(
      item.page_number,
      snippet,
      "material_specifications",
    );
    pushRef(normalizeKey(item.material_name), ref);
  });

  extraction.quantity_takeoff?.forEach((item) => {
    const snippet = item.evidence_snippet || item.item;
    const ref = createExtractionEvidenceRef(item.page_number, snippet, "quantity_takeoff");
    pushRef(normalizeKey(item.item), ref);
  });

  extraction.room_program?.rooms?.forEach((room) => {
    const snippet = room.evidence_snippet || room.room_name;
    const ref = createExtractionEvidenceRef(room.page_number, snippet, "room_program");
    pushRef(normalizeKey(room.room_name), ref);
  });

  const lookupEntries = Array.from(lookup.entries());

  bid.line_items.forEach((lineItem, index) => {
    const normalizedDescription = normalizeKey(lineItem.description);
    const normalizedBasis = normalizeKey(lineItem.basis);
    const seen = new Set<string>();
    const collected: EvidenceRef[] = [];

    const addRefs = (refs?: EvidenceRef[]) => {
      if (!refs) return;
      refs.forEach((ref) => {
        const key = `${ref.page_number}|${ref.snippet || ""}`;
        if (!seen.has(key)) {
          seen.add(key);
          collected.push(ref);
        }
      });
    };

    addRefs(lookup.get(normalizedDescription));
    if (normalizedBasis) {
      addRefs(lookup.get(normalizedBasis));
    }

    if (collected.length === 0 && normalizedDescription) {
      lookupEntries.forEach(([key, refs]) => {
        if (!key) return;
        if (key.includes(normalizedDescription) || normalizedDescription.includes(key)) {
          addRefs(refs);
        }
      });
    }

    if (collected.length > 0) {
      map[index] = collected;
    }
  });

  return map;
};

type BidMode = "conceptual" | "contractor";

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
    quantity_source?: string;
    quantity_confidence?: number;
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
  bid_ready?: boolean;
  estimate_mode?: string;
}

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
}

export function BidTab({ projectId }: BidTabProps) {
  const [bidMode, setBidMode] = useState<BidMode>("conceptual");
  const [bidVersion, setBidVersion] = useState<"original" | "normalized">("original"); // Phase 10.11B
  const [bid, setBid] = useState<BidProposal | null>(null);
  const [bidV2, setBidV2] = useState<BidProposal | null>(null); // Phase 10.11B
  const [normalizationReport, setNormalizationReport] = useState<any | null>(null); // Phase 10.11B
  const [contractorBid, setContractorBid] = useState<ContractorBid | null>(null);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedItemIndex, setSelectedItemIndex] = useState<number | null>(null);
  const [selectedContractorItemId, setSelectedContractorItemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bidReview, setBidReview] = useState<BidReview | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [generatingContractorBid, setGeneratingContractorBid] = useState(false);
  const [generatingContractorPdf, setGeneratingContractorPdf] = useState(false);
  const [contractorPdfExists, setContractorPdfExists] = useState(false);

  // Use evidence index hook (fallback)
  const { getEvidenceForBidItem, documentAnalysis } = useEvidenceIndex(projectId);

  useEffect(() => {
    const loadBid = async () => {
      try {
        // Phase 10.11B: Load both original and normalized bid proposals
        const data = await api.getArtifact<BidProposal>(projectId, "bid_proposal");
        if (!data) {
          setError("Bid proposal not found. The project may still be processing.");
          setLoading(false);
          return;
        }
        setBid(data);
        setError(null);
        
        // Try to load bid_proposal_v2 (normalized)
        const dataV2 = await api.getArtifact<BidProposal>(projectId, "bid_proposal_v2");
        if (dataV2) {
          setBidV2(dataV2);
          // Also try to load normalization report
          const report = await api.getArtifact<any>(projectId, "quantity_normalization_report");
          if (report) {
            setNormalizationReport(report);
          }
        }
        // bid_proposal_v2 is optional, keep using original
        
        // Also load bid_review for evidence_refs
        const reviewData = await api.getArtifact<any>(projectId, "bid_review");
        if (reviewData) {
            console.log("[BidTab] Loaded bid_review:", {
              line_items_count: reviewData.line_items?.length || 0,
              first_item: reviewData.line_items?.[0] ? {
                line_item_index: reviewData.line_items[0].line_item_index,
                evidence_refs_count: reviewData.line_items[0].evidence_refs?.length || 0,
              } : null,
            });
          setBidReview(reviewData);
        }
        // bid_review is optional - null is expected if not available
        // Silently use evidence_index fallback
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setError("Bid proposal not found. The project may still be processing.");
        } else if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load bid proposal.");
        }
      } finally {
        setLoading(false);
      }
    };

    loadBid();
  }, [projectId]);

  useEffect(() => {
    const loadExtraction = async () => {
      try {
        const data = await api.getArtifact<ExtractionResult>(projectId, "extraction_result");
        setExtraction(data);
      } catch (err) {
        setExtraction(null);
        if (err instanceof ApiError && err.status !== 404) {
          console.warn("[BidTab] Failed to load extraction_result artifact:", err);
        }
      }
    };

    loadExtraction();
  }, [projectId]);

  // Load contractor bid when in contractor mode
  useEffect(() => {
    if (bidMode === "contractor") {
      const loadContractorBid = async () => {
        try {
          const data = await api.getContractorBid(projectId);
          setContractorBid(data);
        } catch (err) {
          console.warn("[BidTab] Failed to load contractor bid:", err);
          setContractorBid(null);
        }
      };
      loadContractorBid();
    }
  }, [projectId, bidMode]);

  // Check if contractor PDF exists
  useEffect(() => {
    const checkContractorPdf = async () => {
      try {
        // Try to fetch the PDF (HEAD request would be better, but we'll use GET with error handling)
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`, {
          method: "HEAD",
        });
        setContractorPdfExists(response.ok);
      } catch {
        setContractorPdfExists(false);
      }
    };
    if (bidMode === "contractor" && contractorBid) {
      checkContractorPdf();
    }
  }, [projectId, bidMode, contractorBid]);

  const handleGenerateContractorBid = async () => {
    setGeneratingContractorBid(true);
    try {
      const data = await api.generateContractorBid(projectId);
      setContractorBid(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to generate contractor bid.");
      }
    } finally {
      setGeneratingContractorBid(false);
    }
  };

  const handleGenerateContractorPdf = async () => {
    setGeneratingContractorPdf(true);
    try {
      await api.generateContractorProposalPdf(projectId);
      setError(null);
      // Poll for PDF existence (simple approach - could be improved with job status)
      setTimeout(() => {
        const checkPdf = async () => {
          try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`, {
              method: "HEAD",
            });
            setContractorPdfExists(response.ok);
          } catch {
            setContractorPdfExists(false);
          }
        };
        checkPdf();
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to generate contractor proposal PDF.");
      }
    } finally {
      setGeneratingContractorPdf(false);
    }
  };

  const handleDownloadContractorPdf = () => {
    const url = `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`;
    window.open(url, "_blank");
  };

  // Phase 10.11B: Use normalized version if available and selected
  const currentBid = useMemo(
    () => (bidVersion === "normalized" && bidV2 ? bidV2 : bid),
    [bidVersion, bidV2, bid],
  );

  const extractionEvidenceMap = useMemo(
    () => buildExtractionEvidenceMap(currentBid, extraction),
    [currentBid, extraction],
  );

  const handleOpenEvidence = (itemIndex: number) => {
    setSelectedContractorItemId(null);
    setSelectedItemIndex(itemIndex);
    setEvidenceDrawerOpen(true);
  };
  
  const selectedItem = selectedItemIndex !== null && selectedItemIndex >= 0 && currentBid
    ? currentBid.line_items[selectedItemIndex]
    : null;
  
  // For contractor items, map back to original bid proposal index if it's a base scope item
  let mappedBidItemIndex: number | null = null;
  if (selectedContractorItemId && selectedContractorItemId.startsWith("bid_item_")) {
    // Extract index from item_id like "bid_item_000" -> 0, "bid_item_001" -> 1, etc.
    const indexMatch = selectedContractorItemId.match(/bid_item_(\d+)/);
    if (indexMatch) {
      mappedBidItemIndex = parseInt(indexMatch[1], 10);
      console.log("[BidTab] Mapped contractor item_id to bid index:", {
        item_id: selectedContractorItemId,
        mapped_index: mappedBidItemIndex,
      });
    }
  }

  // Use mapped index if available, otherwise use selectedItemIndex
  const effectiveItemIndex = mappedBidItemIndex !== null ? mappedBidItemIndex : (selectedItemIndex !== null && selectedItemIndex >= 0 ? selectedItemIndex : null);

  // For contractor items (selectedItemIndex === -1), create a placeholder
  const selectedContractorItem = (selectedItemIndex === -1 || selectedContractorItemId !== null) && contractorBid
    ? (() => {
        // Find the contractor item by ID
        for (const section of contractorBid.sections) {
          const item = section.line_items.find(li => li.item_id === selectedContractorItemId);
          if (item) {
            return { description: item.title, division: item.division || "N/A", item_id: item.item_id };
          }
        }
        // Check logistics and permits
        for (const item of [...contractorBid.logistics, ...contractorBid.permits_and_inspections]) {
          if (item.item_id === selectedContractorItemId) {
            return { description: item.title, division: item.division || "N/A", item_id: item.item_id };
          }
        }
        return { description: "Contractor Item", division: "N/A", item_id: null };
      })()
    : null;

  // Get evidence from bid_review if available, otherwise fallback to evidence_index
  // Use effectiveItemIndex which may be mapped from contractor item
  const reviewItem = effectiveItemIndex !== null && effectiveItemIndex >= 0 && bidReview && Array.isArray(bidReview.line_items)
    ? bidReview.line_items.find((item: any) => item.line_item_index === effectiveItemIndex)
    : null;
  
  console.log("[BidTab] Evidence lookup state:", {
    selectedContractorItemId,
    selectedItemIndex,
    mappedBidItemIndex,
    effectiveItemIndex,
    hasBidReview: !!bidReview,
    reviewItemFound: !!reviewItem,
    reviewItemIndex: reviewItem?.line_item_index,
  });

  // Debug logging - log whenever selectedItemIndex or bidReview changes
  useEffect(() => {
    if (selectedItemIndex !== null) {
      console.log("[BidTab] Evidence lookup:", {
        selectedItemIndex,
        hasBidReview: !!bidReview,
        bidReviewKeys: bidReview ? Object.keys(bidReview) : [],
        reviewItemLineItems: bidReview?.line_items?.length || 0,
        reviewItemFound: !!reviewItem,
        reviewItem: reviewItem
          ? {
              line_item_index: reviewItem.line_item_index,
              title: reviewItem.title,
              evidence_refs_count: reviewItem.evidence_refs?.length || 0,
            }
          : null,
        extractionFallbackCount: extractionEvidenceMap[selectedItemIndex]?.length ?? 0,
      });
    }
  }, [selectedItemIndex, bidReview, reviewItem, extractionEvidenceMap]);

  let rawEvidence: EvidenceRef[] = [];

  if (reviewItem?.evidence_refs && reviewItem.evidence_refs.length > 0) {
    console.log("[BidTab] Using evidence_refs from bid_review:", reviewItem.evidence_refs);
    rawEvidence = reviewItem.evidence_refs
      .map((ref): EvidenceRef => {
        const trimmedSnippet = ref.snippet?.trim() ?? null;
        const pageNumber =
          typeof ref.page_number === "number" && Number.isFinite(ref.page_number)
            ? ref.page_number
            : 0;

        const evidenceRef: EvidenceRef = {
          page_number: pageNumber,
          sheet_id: ref.sheet_id ?? null,
          sheet_title: null,
          location_type: null,
          snippet: trimmedSnippet && trimmedSnippet.length > 0 ? trimmedSnippet : null,
          detail_refs: [],
          source: "bid_item",
          bbox: ref.bbox ?? null,
          bbox_source: (ref.bbox_source as EvidenceRef["bbox_source"]) ?? "none",
        };

        return evidenceRef;
      })
      .filter((ref) => ref.page_number > 0 || !!ref.snippet);
    console.log("[BidTab] Mapped rawEvidence:", rawEvidence);
  } else if (effectiveItemIndex !== null && effectiveItemIndex >= 0) {
    console.log("[BidTab] Falling back to evidence_index lookup for index:", effectiveItemIndex);
    const indexedEvidence = getEvidenceForBidItem(effectiveItemIndex);
    if (indexedEvidence.length > 0) {
      rawEvidence = indexedEvidence;
      console.log("[BidTab] Evidence from evidence_index:", rawEvidence);
    } else {
      const extractionFallback = extractionEvidenceMap[effectiveItemIndex] ?? [];
      rawEvidence = extractionFallback;
      console.log("[BidTab] Evidence from extraction_result fallback:", {
        index: effectiveItemIndex,
        count: extractionFallback.length,
        evidence: extractionFallback,
      });
    }
  }
  // If selectedContractorItemId exists but doesn't map to a bid item, evidence will be empty
  
  // Enrich with sheet titles if document_analysis is available
  const selectedEvidence = enrichWithSheetTitles(rawEvidence, documentAnalysis);
  
  // Debug: Log final evidence whenever it changes
  useEffect(() => {
    if (selectedItemIndex !== null) {
      console.log("[BidTab] Final selectedEvidence for drawer:", {
        count: selectedEvidence.length,
        evidence: selectedEvidence,
        willOpenDrawer: evidenceDrawerOpen,
      });
    }
  }, [selectedItemIndex, evidenceDrawerOpen, selectedEvidence]);

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

  if (!bid && !contractorBid) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>No bid proposal data available</AlertDescription>
      </Alert>
    );
  }

  // Render contractor bid or conceptual bid based on mode
  // currentBid is already defined above (line 271)
  const displayBid = bidMode === "contractor" ? contractorBid : currentBid;
  const isContractorMode = bidMode === "contractor";

  // For conceptual bid: group line items by division
  const itemsByDivision: Record<string, BidProposal["line_items"]> = {};
  if (currentBid && !isContractorMode) {
    for (const item of currentBid.line_items) {
      if (!itemsByDivision[item.division]) {
        itemsByDivision[item.division] = [];
      }
      itemsByDivision[item.division].push(item);
    }
  }

  return (
    <div className="space-y-6">
      {/* Bid Mode Toggle */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Bid Summary</CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant={bidMode === "conceptual" ? "default" : "outline"}
                size="sm"
                onClick={() => setBidMode("conceptual")}
              >
                Conceptual
              </Button>
              <Button
                variant={bidMode === "contractor" ? "default" : "outline"}
                size="sm"
                onClick={() => setBidMode("contractor")}
              >
                Contractor
              </Button>
              {/* Phase 10.11B: Original vs Normalized toggle (only show if v2 exists and in conceptual mode) */}
              {!isContractorMode && bidV2 && (
                <>
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
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {isContractorMode && !contractorBid && (
              <Alert className="mb-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription className="flex items-center justify-between">
                  <span>Contractor bid not generated yet.</span>
                  <Button
                    size="sm"
                    onClick={handleGenerateContractorBid}
                    disabled={generatingContractorBid}
                  >
                    {generatingContractorBid ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate Contractor Bid
                      </>
                    )}
                  </Button>
                </AlertDescription>
              </Alert>
            )}
            {isContractorMode && contractorBid && (
              <div className="flex items-center gap-2 mb-4">
                {contractorPdfExists ? (
                  <Button
                    size="sm"
                    variant="default"
                    onClick={handleDownloadContractorPdf}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download Contractor Proposal PDF
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleGenerateContractorPdf}
                    disabled={generatingContractorPdf}
                  >
                    {generatingContractorPdf ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Generating PDF...
                      </>
                    ) : (
                      <>
                        <FileText className="h-4 w-4 mr-2" />
                        Generate Contractor Proposal PDF
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}
            {/* Phase 1: Excel Export Download */}
            {!isContractorMode && currentBid && (
              <div className="flex items-center gap-2 mb-4">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    try {
                      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";
                      const url = `${apiBase}/projects/${projectId}/artifacts/bid_export`;
                      const response = await fetch(url);
                      if (!response.ok) {
                        if (response.status === 404) {
                          alert("Excel export not available yet. The project may still be processing.");
                          return;
                        }
                        throw new Error(`Failed to download: ${response.statusText}`);
                      }
                      const blob = await response.blob();
                      const downloadUrl = window.URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = downloadUrl;
                      a.download = `bid_export_${projectId}.xlsx`;
                      document.body.appendChild(a);
                      a.click();
                      window.URL.revokeObjectURL(downloadUrl);
                      document.body.removeChild(a);
                    } catch (err) {
                      console.error("Excel download error:", err);
                      alert("Failed to download Excel export. It may not be available yet.");
                    }
                  }}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Download Excel Export
                </Button>
              </div>
            )}
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="text-lg font-semibold">Total Cost:</span>
                {isContractorMode && (
                  <Badge variant="secondary" className="text-xs">
                    CONTRACTOR (SYNTHESIZED)
                  </Badge>
                )}
                {!isContractorMode && (
                  <Badge variant="outline" className="text-xs">
                    CONCEPTUAL
                  </Badge>
                )}
              </div>
              <span className="text-2xl font-bold">
                ${displayBid
                  ? (isContractorMode
                      ? (displayBid as ContractorBid).total_bid
                      : (displayBid as BidProposal).summary.total_cost
                    ).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "0.00"}
              </span>
            </div>
            {!isContractorMode && currentBid && (
              <>
                {currentBid.bid_ready !== undefined && (
                  <div className="flex items-center gap-2">
                    <span>Bid Ready:</span>
                    <Badge variant={currentBid.bid_ready ? "default" : "destructive"}>
                      {currentBid.bid_ready ? "Yes" : "No"}
                    </Badge>
                  </div>
                )}
                {currentBid.estimate_mode && (
                  <div className="flex items-center gap-2">
                    <span>Estimate Mode:</span>
                    <Badge variant="outline">{currentBid.estimate_mode}</Badge>
                  </div>
                )}
                {bidVersion === "normalized" && (
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">Normalized</Badge>
                    {normalizationReport && (
                      <span className="text-xs text-muted-foreground">
                        {normalizationReport.items_normalized || 0} items normalized
                      </span>
                    )}
                  </div>
                )}
              </>
            )}
            {isContractorMode && contractorBid && (
              <div className="space-y-1 text-sm text-muted-foreground">
                {Object.entries(contractorBid.subtotals).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <span className="capitalize">{key.replace(/_/g, " ")}:</span>
                    <span>${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Render Conceptual Bid */}
      {!isContractorMode && currentBid && Object.entries(itemsByDivision).map(([division, items]) => (
        <Card key={division}>
          <CardHeader>
            <CardTitle>{division}</CardTitle>
            <CardDescription>
              Subtotal: ${currentBid.summary.cost_by_division[division]?.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }) || "0.00"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit Cost</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="w-[100px]">Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, idx) => {
                  const globalIndex = currentBid.line_items.findIndex(li => li === item);
                  
                  return (
                    <TableRow key={idx}>
                      <TableCell className="font-medium">{item.description}</TableCell>
                      <TableCell className="text-right">
                        {item.quantity !== null
                          ? `${item.quantity.toLocaleString()} ${item.unit || ""}`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {item.unit_cost !== null
                          ? `$${item.unit_cost.toFixed(2)}`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        ${item.total_cost.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </TableCell>
                      <TableCell>
                        {item.quantity_source && (
                          <Badge variant="outline" className="text-xs">
                            {getTerm(item.quantity_source)}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleOpenEvidence(globalIndex)}
                          className="flex items-center gap-1"
                        >
                          <FileText className="h-4 w-4" />
                          Evidence
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}

      {/* Render Contractor Bid Sections */}
      {isContractorMode && contractorBid && contractorBid.sections.map((section) => (
        <Card key={section.section_id}>
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
            <CardDescription>
              Subtotal: ${section.subtotal.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit Cost</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Basis</TableHead>
                  <TableHead className="w-[100px]">Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {section.line_items.map((item, idx) => (
                  <TableRow key={item.item_id || idx}>
                    <TableCell className="font-medium">{item.title}</TableCell>
                    <TableCell className="text-right">
                      {item.quantity !== null && item.quantity !== undefined
                        ? `${item.quantity.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${item.unit || ""}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {item.unit_cost !== null && item.unit_cost !== undefined
                        ? `$${item.unit_cost.toFixed(2)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      ${item.total_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.basis}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          // Map contractor item back to bid proposal if it's a base scope item
                          if (item.item_id.startsWith("bid_item_")) {
                            const indexMatch = item.item_id.match(/bid_item_(\d+)/);
                            if (indexMatch) {
                              const bidIndex = parseInt(indexMatch[1], 10);
                              console.log("[BidTab] Opening evidence for contractor item, mapped to bid index:", bidIndex);
                              setSelectedItemIndex(bidIndex);
                              setSelectedContractorItemId(null);
                            } else {
                              console.log("[BidTab] Could not parse bid index from item_id:", item.item_id);
                              setSelectedItemIndex(-1);
                              setSelectedContractorItemId(item.item_id);
                            }
                          } else {
                            // For expanded scope items (logistics, permits, labor), use item_id
                            console.log("[BidTab] Opening evidence for expanded scope item:", item.item_id);
                            setSelectedItemIndex(-1);
                            setSelectedContractorItemId(item.item_id);
                          }
                          setEvidenceDrawerOpen(true);
                        }}
                        className="flex items-center gap-1"
                      >
                        <FileText className="h-4 w-4" />
                        Evidence
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}

      {/* Contractor Bid: Permits & Inspections */}
      {isContractorMode && contractorBid && contractorBid.permits_and_inspections.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Permits & Inspections</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Basis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contractorBid.permits_and_inspections.map((item) => (
                  <TableRow key={item.item_id}>
                    <TableCell className="font-medium">{item.title}</TableCell>
                    <TableCell className="text-right font-medium">
                      ${item.total_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.basis}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Contractor Bid: Logistics */}
      {isContractorMode && contractorBid && contractorBid.logistics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Logistics</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit Cost</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Basis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contractorBid.logistics.map((item) => (
                  <TableRow key={item.item_id}>
                    <TableCell className="font-medium">{item.title}</TableCell>
                    <TableCell className="text-right">
                      {item.quantity !== null && item.quantity !== undefined
                        ? `${item.quantity.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${item.unit || ""}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {item.unit_cost !== null && item.unit_cost !== undefined
                        ? `$${item.unit_cost.toFixed(2)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      ${item.total_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.basis}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Contractor Bid: Exclusions & Assumptions */}
      {isContractorMode && contractorBid && (
        <>
          {contractorBid.exclusions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Exclusions</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {contractorBid.exclusions.map((exclusion, idx) => (
                    <li key={idx} className="text-muted-foreground">{exclusion}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          {contractorBid.assumptions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Assumptions</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {contractorBid.assumptions.map((assumption, idx) => (
                    <li key={idx} className="text-muted-foreground">{assumption}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Conceptual Bid: Allowances */}
      {!isContractorMode && bid && bid.allowances.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Allowances</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bid.allowances.map((allowance, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-medium">{allowance.name}</TableCell>
                    <TableCell className="text-right font-medium">
                      ${allowance.amount.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell>{allowance.notes}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Conceptual Bid: Clarifications */}
      {!isContractorMode && bid && bid.clarifications.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Clarifications</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {bid.clarifications.map((clarification, idx) => (
                <Alert
                  key={idx}
                  variant={
                    clarification.severity === "critical"
                      ? "destructive"
                      : clarification.severity === "warning"
                      ? "default"
                      : "default"
                  }
                >
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{clarification.text}</AlertDescription>
                </Alert>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Evidence Drawer */}
      <EvidenceDrawer
        open={evidenceDrawerOpen}
        onOpenChange={setEvidenceDrawerOpen}
        title={
          selectedItem
            ? `${selectedItem.division} — ${selectedItem.description}`
            : selectedContractorItem
            ? `${selectedContractorItem.division} — ${selectedContractorItem.description}`
            : "Evidence"
        }
        subtitle={
          selectedItem
            ? `Line item ${selectedItemIndex !== null ? selectedItemIndex + 1 : ""}`
            : selectedContractorItem
            ? "Contractor Item (SYNTHESIZED)"
            : undefined
        }
        evidence={selectedEvidence} // Use selectedEvidence which may include mapped evidence for base scope items
        projectId={projectId}
        initialPage={selectedEvidence.length > 0 ? selectedEvidence[0].page_number : undefined}
      />
    </div>
  );
}

