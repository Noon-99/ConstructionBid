/** Terminology normalization (Phase 9.1).
 * 
 * Replaces internal wording with contractor-friendly language.
 */

export const TERMINOLOGY = {
  // Quantity sources
  "derived_from_dimensions": "Measured from drawings",
  "heuristic": "Estimated — review recommended",
  "explicit_takeoff": "Verified",
  "recovered": "Automatically verified from drawings",
  "allowance": "Allowance",
  "unknown": "Unknown — review required",
  
  // Flags
  "recovered_item": "Automatically verified from drawings",
  "heuristic_quantity": "Estimated — review recommended",
  "suspicious_unit_cost": "Review recommended",
  "suspicious_quantity": "Review recommended",
  
  // Geometry quality
  "derived_from_area": "Incomplete geometry — review required",
  "authoritative": "Verified",
  "partial": "Incomplete geometry — review required",
  
  // General
  "evidence_index": "Drawing references",
  "auto-recovered": "Automatically verified from drawings",
  "partial_geometry": "Incomplete geometry — review required",
} as const;

export type TerminologyKey = keyof typeof TERMINOLOGY;

/**
 * Get contractor-friendly terminology for a key.
 */
export function getTerm(key: TerminologyKey | string): string {
  return TERMINOLOGY[key as TerminologyKey] || key;
}

/**
 * Badge variants for standardized badges.
 */
export const BADGE_VARIANTS = {
  verified: "default" as const,
  reviewRecommended: "secondary" as const,
  automaticallyVerified: "secondary" as const,
  blockingIssue: "destructive" as const,
} as const;

/**
 * Get badge variant for a flag or status.
 */
export function getBadgeVariant(flag: string, quantitySource?: string): "default" | "secondary" | "destructive" | "outline" {
  // Blocking issues
  if (flag === "suspicious_unit_cost" || flag === "suspicious_quantity") {
    return BADGE_VARIANTS.reviewRecommended;
  }
  
  // Automatically verified
  if (flag === "recovered_item" || quantitySource === "recovered") {
    return BADGE_VARIANTS.automaticallyVerified;
  }
  
  // Review recommended
  if (flag === "heuristic_quantity" || quantitySource === "heuristic") {
    return BADGE_VARIANTS.reviewRecommended;
  }
  
  // Verified
  if (quantitySource === "explicit_takeoff") {
    return BADGE_VARIANTS.verified;
  }
  
  return "outline";
}

/**
 * Get badge label for a flag or status.
 */
export function getBadgeLabel(flag: string, quantitySource?: string): string {
  // Use terminology mapping
  if (TERMINOLOGY[flag as TerminologyKey]) {
    return TERMINOLOGY[flag as TerminologyKey];
  }
  
  if (quantitySource && TERMINOLOGY[quantitySource as TerminologyKey]) {
    return TERMINOLOGY[quantitySource as TerminologyKey];
  }
  
  // Fallback: humanize the key
  return flag.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

