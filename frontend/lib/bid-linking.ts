/**
 * Utilities for linking 3D zones to bid line items.
 */

export interface BidLineItem {
  division: string;
  description: string;
  quantity?: number | null;
  unit?: string | null;
  total_cost: number;
  basis: string;
}

/**
 * Match a zone name to bid line items using exact match or keyword overlap.
 */
export function findLinkedBidItems(
  zoneName: string,
  bidItems: BidLineItem[]
): BidLineItem[] {
  const zoneLower = zoneName.toLowerCase();
  const matches: BidLineItem[] = [];

  // Common keywords that might appear in both zone names and bid descriptions
  const keywords = [
    "parapet",
    "lintel",
    "flashing",
    "gymnasium",
    "gym",
    "kitchen",
    "bathroom",
    "restroom",
    "office",
    "classroom",
    "corridor",
    "hallway",
    "lobby",
    "entry",
    "stair",
    "elevator",
    "mechanical",
    "electrical",
    "plumbing",
    "roof",
    "wall",
    "floor",
    "ceiling",
    "window",
    "door",
  ];

  for (const item of bidItems) {
    const descLower = item.description.toLowerCase();

    // Exact match (zone name appears in description or vice versa)
    if (descLower.includes(zoneLower) || zoneLower.includes(descLower)) {
      matches.push(item);
      continue;
    }

    // Keyword overlap
    const zoneKeywords = keywords.filter((kw) => zoneLower.includes(kw));
    const descKeywords = keywords.filter((kw) => descLower.includes(kw));

    if (zoneKeywords.length > 0 && descKeywords.length > 0) {
      // Check if there's any overlap
      const overlap = zoneKeywords.filter((kw) => descKeywords.includes(kw));
      if (overlap.length > 0) {
        matches.push(item);
      }
    }
  }

  return matches;
}






