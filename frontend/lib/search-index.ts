/**
 * Search index builder for 3D viewer (Phase 8.5).
 * Deterministic, frontend-only search across extracted entities.
 */

export type SearchEntryType = "building" | "zone" | "region" | "bid_item" | "detail";

export interface SearchEntry {
  id: string;
  type: SearchEntryType;
  title: string;
  keywords: string[];
  meta: {
    division?: string;
    cost?: number;
    pages?: number[];
    region_type?: string;
    building_type?: string;
    zone_type?: string;
    detail_id?: string;
    sheet_id?: string;
  };
  target: {
    type: "bbox" | "bid_item" | "detail";
    bbox?: {
      min: { x: number; y: number; z: number };
      max: { x: number; y: number; z: number };
    };
    bid_item_index?: number;
    detail_id?: string;
    region_id?: string;
    zone_name?: string;
    building_id?: string;
  };
}

interface Model3D {
  buildings?: Array<{
    building_id?: string | null;
    building_type: string;
    bounding_box: {
      min: { x: number; y: number; z: number };
      max: { x: number; y: number; z: number };
    };
  }>;
  work_zones?: Array<{
    zone_name: string;
    bounding_box?: {
      min: { x: number; y: number; z: number };
      max: { x: number; y: number; z: number };
    } | null;
    zone_type?: string | null;
  }>;
  cross_section_regions?: Array<{
    region_id: string;
    region_type: string;
    bounding_box: {
      min: { x: number; y: number; z: number };
      max: { x: number; y: number; z: number };
    };
  }>;
}

interface BidProposal {
  line_items?: Array<{
    division: string;
    description: string;
    total_cost: number;
  }>;
}

interface EvidenceIndex {
  zone_evidence?: Array<{
    zone_id: string;
    evidence_references: Array<{
      page_number: number;
    }>;
  }>;
  bid_item_evidence?: Array<{
    line_item_index: number;
    evidence_references: Array<{
      page_number: number;
    }>;
  }>;
}

interface DetailOverlayIndex {
  regions?: Array<{
    region_id: string;
    region_type: string;
    detail_refs: Array<{
      detail_id: string;
      sheet_id: string;
      detail_label: string;
      page_number: number;
    }>;
    evidence_pages: number[];
  }>;
}

/**
 * Tokenize text into normalized keywords.
 */
function tokenize(text: string): string[] {
  if (!text) return [];
  // Split on non-alphanumeric, convert to lowercase, remove stopwords
  const stopwords = new Set([
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "should", "could", "may", "might", "must", "can",
  ]);
  
  const tokens = text
    .toLowerCase()
    .split(/[_\-\s]+/)
    .map(t => t.replace(/[^a-z0-9]/g, ""))
    .filter(t => t.length > 1 && !stopwords.has(t));
  
  return tokens;
}

/**
 * Build search index from available artifacts.
 */
export function buildSearchIndex({
  model3d,
  bid,
  evidenceIndex,
  detailOverlayIndex,
}: {
  model3d?: Model3D | null;
  bid?: BidProposal | null;
  evidenceIndex?: EvidenceIndex | null;
  detailOverlayIndex?: DetailOverlayIndex | null;
}): SearchEntry[] {
  const entries: SearchEntry[] = [];

  // Buildings
  if (model3d?.buildings) {
    for (const building of model3d.buildings) {
      const buildingId = building.building_id || "unknown";
      const title = `Building: ${buildingId} (${building.building_type})`;
      const keywords = tokenize(`${buildingId} ${building.building_type} building`);
      
      entries.push({
        id: `building_${buildingId}`,
        type: "building",
        title,
        keywords,
        meta: {
          building_type: building.building_type,
        },
        target: {
          type: "bbox",
          bbox: building.bounding_box,
          building_id: buildingId,
        },
      });
    }
  }

  // Zones
  if (model3d?.work_zones) {
    for (const zone of model3d.work_zones) {
      if (!zone.zone_name) continue;
      
      const keywords = tokenize(`${zone.zone_name} ${zone.zone_type || ""} zone`);
      const pages: number[] = [];
      
      // Get pages from evidence_index
      if (evidenceIndex?.zone_evidence) {
        const zoneEvidence = evidenceIndex.zone_evidence.find(
          (ze) => ze.zone_id === zone.zone_name
        );
        if (zoneEvidence) {
          pages.push(...zoneEvidence.evidence_references.map((ref) => ref.page_number));
        }
      }
      
      entries.push({
        id: `zone_${zone.zone_name}`,
        type: "zone",
        title: `Zone: ${zone.zone_name}`,
        keywords,
        meta: {
          zone_type: zone.zone_type || undefined,
          pages: pages.length > 0 ? pages : undefined,
        },
        target: {
          type: "bbox",
          bbox: zone.bounding_box || undefined,
          zone_name: zone.zone_name,
        },
      });
    }
  }

  // Cross-section regions
  if (model3d?.cross_section_regions) {
    for (const region of model3d.cross_section_regions) {
      const regionTypeLabel = region.region_type.replace(/_/g, " ");
      const title = `${regionTypeLabel}: ${region.region_id}`;
      const keywords = tokenize(`${region.region_id} ${region.region_type} region cross section`);
      
      const pages: number[] = [];
      if (detailOverlayIndex?.regions) {
        const overlayRegion = detailOverlayIndex.regions.find(
          (r) => r.region_id === region.region_id
        );
        if (overlayRegion) {
          pages.push(...overlayRegion.evidence_pages);
        }
      }
      
      entries.push({
        id: `region_${region.region_id}`,
        type: "region",
        title,
        keywords,
        meta: {
          region_type: region.region_type,
          pages: pages.length > 0 ? pages : undefined,
        },
        target: {
          type: "bbox",
          bbox: region.bounding_box,
          region_id: region.region_id,
        },
      });
    }
  }

  // Bid line items
  if (bid?.line_items) {
    for (let idx = 0; idx < bid.line_items.length; idx++) {
      const item = bid.line_items[idx];
      const title = `${item.division} — ${item.description}`;
      const keywords = tokenize(`${item.division} ${item.description} bid item line`);
      
      const pages: number[] = [];
      if (evidenceIndex?.bid_item_evidence) {
        const itemEvidence = evidenceIndex.bid_item_evidence.find(
          (e) => e.line_item_index === idx
        );
        if (itemEvidence) {
          pages.push(...itemEvidence.evidence_references.map((ref) => ref.page_number));
        }
      }
      
      entries.push({
        id: `bid_item_${idx}`,
        type: "bid_item",
        title,
        keywords,
        meta: {
          division: item.division,
          cost: item.total_cost,
          pages: pages.length > 0 ? pages : undefined,
        },
        target: {
          type: "bid_item",
          bid_item_index: idx,
        },
      });
    }
  }

  // Details (from detail_overlay_index)
  if (detailOverlayIndex?.regions) {
    for (const region of detailOverlayIndex.regions) {
      for (const detailRef of region.detail_refs) {
        const title = `${detailRef.sheet_id} ${detailRef.detail_label}`;
        const keywords = tokenize(
          `${detailRef.detail_id} ${detailRef.sheet_id} ${detailRef.detail_label} detail`
        );
        
        entries.push({
          id: `detail_${detailRef.detail_id}`,
          type: "detail",
          title,
          keywords,
          meta: {
            detail_id: detailRef.detail_id,
            sheet_id: detailRef.sheet_id,
            pages: [detailRef.page_number],
          },
          target: {
            type: "detail",
            detail_id: detailRef.detail_id,
            region_id: region.region_id,
          },
        });
      }
    }
  }

  return entries;
}

/**
 * Search entries with scoring.
 */
export interface SearchResult {
  entry: SearchEntry;
  score: number;
}

/**
 * Search the index with token overlap scoring.
 */
export function searchIndex(
  index: SearchEntry[],
  query: string,
  limit: number = 10
): SearchResult[] {
  if (!query || query.trim().length === 0) {
    return [];
  }

  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) {
    return [];
  }

  const results: SearchResult[] = [];

  for (const entry of index) {
    let score = 0;
    let matchedTokens = 0;

    // Token overlap scoring
    for (const queryToken of queryTokens) {
      for (const keyword of entry.keywords) {
        if (keyword === queryToken) {
          score += 10; // Exact match
          matchedTokens++;
        } else if (keyword.startsWith(queryToken)) {
          score += 5; // Starts-with match (boosted)
          matchedTokens++;
        } else if (keyword.includes(queryToken)) {
          score += 2; // Contains match
          matchedTokens++;
        }
      }
    }

    // Boost if all query tokens matched
    if (matchedTokens === queryTokens.length) {
      score += 20;
    }

    // Boost if title starts with query
    const titleLower = entry.title.toLowerCase();
    const queryLower = query.toLowerCase();
    if (titleLower.startsWith(queryLower)) {
      score += 15;
    }

    if (score > 0) {
      results.push({ entry, score });
    }
  }

  // Sort by score (descending), then by title
  results.sort((a, b) => {
    if (b.score !== a.score) {
      return b.score - a.score;
    }
    return a.entry.title.localeCompare(b.entry.title);
  });

  return results.slice(0, limit);
}






