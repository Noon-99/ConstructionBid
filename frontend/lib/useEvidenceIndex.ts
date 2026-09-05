/** Evidence index hook (Phase 8.1).
 * 
 * Fetches evidence_index once per project page and caches in memory.
 */

import { useState, useEffect, useMemo } from "react";
import { api, ApiError } from "@/lib/api";
import {
  getEvidenceForBidItem,
  getEvidenceForZone,
  getEvidenceForDetail,
  enrichWithSheetTitles,
  type EvidenceRef,
} from "@/lib/evidence-normalizer";

// EvidenceIndex type matching backend schema
interface EvidenceIndex {
  project_id: string;
  bid_item_evidence: Array<{
    line_item_index: number;
    division: string;
    description: string;
    evidence_references: Array<{
      page_number: number;
      sheet_id?: string | null;
      evidence_snippet: string;
      location_type?: string | null;
    }>;
    quantity_source?: string | null;
    basis: string;
  }>;
  zone_evidence: Array<{
    zone_id: string;
    zone_type: string;
    label?: string | null;
    evidence_references: Array<{
      page_number: number;
      sheet_id?: string | null;
      evidence_snippet: string;
      location_type?: string | null;
    }>;
    linked_bid_items: number[];
  }>;
  detail_evidence: Array<{
    detail_id: string;
    detail_type: string;
    sheet_id: string;
    detail_label: string;
    evidence_references: Array<{
      page_number: number;
      sheet_id?: string | null;
      evidence_snippet: string;
      location_type?: string | null;
    }>;
    linked_zones: string[];
    linked_openings: string[];
    linked_bid_items: number[];
  }>;
  generated_at: string;
}

interface DocumentAnalysis {
  sheets?: Array<{
    sheet_id: string;
    title?: string | null;
  }>;
}

// EvidenceBboxIndex type matching backend schema (Phase 8.6D)
interface EvidenceBboxIndex {
  project_id: string;
  generated_at: string;
  entries: Array<{
    evidence_id: string;
    page_number: number;
    snippet: string;
    bbox: { x0: number; y0: number; x1: number; y1: number } | null;
    bbox_source: "pdf" | "image" | "none";
    match_confidence?: number | null;
    match_method?: string | null;
  }>;
  metrics: {
    bbox_match_rate?: number;
    total_evidence?: number;
    matched_count?: number;
    avg_match_confidence?: number;
    ocr_pages_processed?: number;
  };
}

export function useEvidenceIndex(projectId: string) {
  const [evidenceIndex, setEvidenceIndex] = useState<EvidenceIndex | null>(null);
  const [documentAnalysis, setDocumentAnalysis] = useState<DocumentAnalysis | null>(null);
  const [bboxIndex, setBboxIndex] = useState<EvidenceBboxIndex | null>(null); // Phase 8.6D
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadEvidence = async () => {
      try {
        // First, get list of available artifacts
        const artifactsList = await api.listArtifacts(projectId);
        const availableArtifacts = new Set(artifactsList.artifacts.map(a => a.name));

        // Load evidence_index only if available
        if (availableArtifacts.has("evidence_index")) {
          const evidence = await api.getArtifact<EvidenceIndex>(projectId, "evidence_index");
          if (!cancelled) {
            setEvidenceIndex(evidence);
          }
        } else {
          if (!cancelled) {
            setEvidenceIndex(null);
          }
        }

        // Optionally load document_analysis for sheet titles (if available)
        if (availableArtifacts.has("document_analysis")) {
          const analysis = await api.getArtifact<DocumentAnalysis>(
            projectId,
            "document_analysis"
          );
          if (!cancelled) {
            setDocumentAnalysis(analysis);
          }
        }

        // Optionally load evidence_bbox_index (Phase 8.6D) - only if feature enabled and available
        const FEATURE_EVIDENCE_BBOX = process.env.NEXT_PUBLIC_FEATURE_EVIDENCE_BBOX !== "false";
        if (FEATURE_EVIDENCE_BBOX && availableArtifacts.has("evidence_bbox_index")) {
          const bbox = await api.getArtifact<EvidenceBboxIndex>(
            projectId,
            "evidence_bbox_index"
          );
          if (!cancelled) {
            setBboxIndex(bbox);
          }
        } else {
          if (!cancelled) {
            setBboxIndex(null);
          }
        }

        if (!cancelled) {
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError("Failed to load evidence index");
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadEvidence();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Helper methods
  const getEvidenceForBidItemIndex = useMemo(
    () => (lineItemIndex: number): EvidenceRef[] => {
      const refs = getEvidenceForBidItem(evidenceIndex, lineItemIndex);
      return enrichWithSheetTitles(refs, documentAnalysis);
    },
    [evidenceIndex, documentAnalysis]
  );

  const getEvidenceForZoneId = useMemo(
    () => (zoneId: string): EvidenceRef[] => {
      const refs = getEvidenceForZone(evidenceIndex, zoneId);
      return enrichWithSheetTitles(refs, documentAnalysis);
    },
    [evidenceIndex, documentAnalysis]
  );

  const getEvidenceForDetailId = useMemo(
    () => (detailId: string): EvidenceRef[] => {
      const refs = getEvidenceForDetail(evidenceIndex, detailId);
      return enrichWithSheetTitles(refs, documentAnalysis);
    },
    [evidenceIndex, documentAnalysis]
  );

  return {
    evidenceIndex,
    documentAnalysis, // Expose for enrichment
    loading,
    error,
    getEvidenceForBidItem: getEvidenceForBidItemIndex,
    getEvidenceForZone: getEvidenceForZoneId,
    getEvidenceForDetail: getEvidenceForDetailId,
  };
}

