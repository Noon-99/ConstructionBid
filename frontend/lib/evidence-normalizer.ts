/** Evidence normalization layer (Phase 8.1).
 * 
 * Converts various evidence structures into one UI-safe shape.
 */

export interface EvidenceRef {
  page_number: number;
  sheet_id?: string | null;
  sheet_title?: string | null;
  location_type?: string | null; // e.g., "detail", "note", "schedule"
  snippet?: string | null;
  detail_refs?: string[]; // e.g., ["S-011 Detail 4"]
  source?: "bid_item" | "zone" | "detail" | "extraction";
  bbox?: { x0: number; y0: number; x1: number; y1: number } | null; // Phase 8.6A/8.6D
  bbox_source?: "none" | "vision_box" | "heuristic" | "pdf" | "image" | null; // Phase 8.6A/8.6D
}

interface EvidenceReference {
  page_number: number;
  sheet_id?: string | null;
  evidence_snippet: string;
  location_type?: string | null;
  bbox?: { x0: number; y0: number; x1: number; y1: number } | null; // Phase 8.6A
  bbox_source?: "none" | "vision_box" | "heuristic" | null; // Phase 8.6A
}

interface BidItemEvidence {
  line_item_index: number;
  division: string;
  description: string;
  evidence_references: EvidenceReference[];
  quantity_source?: string | null;
  basis: string;
}

interface ZoneEvidence {
  zone_id: string;
  zone_type: string;
  label?: string | null;
  evidence_references: EvidenceReference[];
  linked_bid_items: number[];
}

interface DetailEvidence {
  detail_id: string;
  detail_type: string;
  sheet_id: string;
  detail_label: string;
  evidence_references: EvidenceReference[];
  linked_zones: string[];
  linked_openings: string[];
  linked_bid_items: number[];
}

interface EvidenceIndex {
  project_id: string;
  bid_item_evidence: BidItemEvidence[];
  zone_evidence: ZoneEvidence[];
  detail_evidence: DetailEvidence[];
  generated_at: string;
}

interface SheetInfo {
  sheet_id: string;
  title?: string | null;
}

interface DocumentAnalysis {
  sheets?: SheetInfo[];
}

/**
 * Normalize evidence references from evidence_index.
 * Deduplicates identical refs and sorts by page_number.
 */
export function normalizeEvidenceRefs(
  evidenceRefs: EvidenceReference[],
  source: "bid_item" | "zone" | "detail",
  detailRefs?: string[]
): EvidenceRef[] {
  // Deduplicate by page_number + snippet (normalized)
  const seen = new Set<string>();
  const normalized: EvidenceRef[] = [];

  for (const ref of evidenceRefs) {
    const key = `${ref.page_number}:${ref.evidence_snippet.trim().toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);

    normalized.push({
      page_number: ref.page_number,
      sheet_id: ref.sheet_id || null,
      sheet_title: null, // Will be enriched from document_analysis if available
      location_type: ref.location_type || null,
      snippet: ref.evidence_snippet || null,
      detail_refs: detailRefs || [],
      source,
      bbox: ref.bbox || null, // Phase 8.6A
      bbox_source: ref.bbox_source || "none", // Phase 8.6A
    });
  }

  // Sort by page_number ascending
  normalized.sort((a, b) => a.page_number - b.page_number);

  return normalized;
}

/**
 * Get evidence refs for a bid item.
 */
export function getEvidenceForBidItem(
  evidenceIndex: EvidenceIndex | null,
  lineItemIndex: number
): EvidenceRef[] {
  if (!evidenceIndex) return [];

  const bidEvidence = evidenceIndex.bid_item_evidence.find(
    (e) => e.line_item_index === lineItemIndex
  );

  if (!bidEvidence || !bidEvidence.evidence_references.length) {
    return [];
  }

  // Extract detail refs from basis if present
  const detailRefs: string[] = [];
  if (bidEvidence.basis) {
    // Look for patterns like "Detail refs: DET-001, S-011-D4"
    const detailMatch = bidEvidence.basis.match(/Detail refs?:\s*([^\n]+)/i);
    if (detailMatch) {
      detailRefs.push(
        ...detailMatch[1]
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      );
    }
  }

  return normalizeEvidenceRefs(
    bidEvidence.evidence_references,
    "bid_item",
    detailRefs.length > 0 ? detailRefs : undefined
  );
}

/**
 * Get evidence refs for a zone.
 */
export function getEvidenceForZone(
  evidenceIndex: EvidenceIndex | null,
  zoneId: string
): EvidenceRef[] {
  if (!evidenceIndex) return [];

  const zoneEvidence = evidenceIndex.zone_evidence.find(
    (e) => e.zone_id === zoneId
  );

  if (!zoneEvidence || !zoneEvidence.evidence_references.length) {
    return [];
  }

  return normalizeEvidenceRefs(zoneEvidence.evidence_references, "zone");
}

/**
 * Get evidence refs for a detail.
 */
export function getEvidenceForDetail(
  evidenceIndex: EvidenceIndex | null,
  detailId: string
): EvidenceRef[] {
  if (!evidenceIndex) return [];

  const detailEvidence = evidenceIndex.detail_evidence.find(
    (e) => e.detail_id === detailId
  );

  if (!detailEvidence || !detailEvidence.evidence_references.length) {
    return [];
  }

  // Include detail label as a detail ref
  const detailRef = `${detailEvidence.sheet_id} ${detailEvidence.detail_label}`;

  return normalizeEvidenceRefs(
    detailEvidence.evidence_references,
    "detail",
    [detailRef]
  );
}

/**
 * Enrich evidence refs with sheet titles from document_analysis.
 */
export function enrichWithSheetTitles(
  refs: EvidenceRef[],
  documentAnalysis: DocumentAnalysis | null
): EvidenceRef[] {
  if (!documentAnalysis?.sheets) return refs;

  const sheetMap = new Map<string, string>();
  for (const sheet of documentAnalysis.sheets) {
    if (sheet.sheet_id && sheet.title) {
      sheetMap.set(sheet.sheet_id, sheet.title);
    }
  }

  return refs.map((ref) => ({
    ...ref,
    sheet_title: ref.sheet_id ? sheetMap.get(ref.sheet_id) || null : null,
  }));
}

/**
 * Create a stable key for a bid item (for matching when IDs are missing).
 */
export function createBidItemKey(
  division: string,
  description: string,
  quantity: number | null,
  unit: string | null
): string {
  // Simple deterministic key - could use hash if needed
  return `${division}:${description}:${quantity ?? "null"}:${unit ?? "null"}`;
}

