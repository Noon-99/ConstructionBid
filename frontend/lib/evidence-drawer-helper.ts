/** Evidence drawer helper (Phase 8.6B).
 * 
 * Centralized function for opening EvidenceDrawer from anywhere in the app.
 */

import type { EvidenceRef } from "./evidence-normalizer";

export interface OpenEvidenceDrawerParams {
  projectId: string;
  evidenceRefs: EvidenceRef[];
  initialPage?: number; // 1-based page number
  focusSnippet?: number; // Optional index to highlight
  source: "bid" | "zone" | "region" | "detail" | "search";
  title: string;
  subtitle?: string;
  onOpen: (params: {
    open: boolean;
    title: string;
    subtitle?: string;
    evidence: EvidenceRef[];
    initialPage?: number;
    initialEvidenceIndex?: number;
  }) => void;
}

/**
 * Open EvidenceDrawer with standardized parameters.
 * 
 * Derives initialPage from evidence if not provided.
 * Handles empty evidence gracefully.
 */
export function openEvidenceDrawer(params: OpenEvidenceDrawerParams): void {
  const {
    projectId,
    evidenceRefs,
    initialPage,
    focusSnippet,
    source,
    title,
    subtitle,
    onOpen,
  } = params;

  // Derive initial page if not provided
  let derivedPage: number | undefined = initialPage;
  if (!derivedPage && evidenceRefs.length > 0) {
    // Use first page from evidence
    derivedPage = evidenceRefs[0].page_number;
  }

  // Determine initial evidence index
  let initialEvidenceIndex: number | undefined = focusSnippet;
  if (initialEvidenceIndex === undefined && derivedPage && evidenceRefs.length > 0) {
    // Find first evidence ref on the initial page
    const firstOnPage = evidenceRefs.findIndex(
      (ref) => ref.page_number === derivedPage
    );
    if (firstOnPage >= 0) {
      initialEvidenceIndex = firstOnPage;
    }
  }

  // Open drawer
  onOpen({
    open: true,
    title,
    subtitle,
    evidence: evidenceRefs,
    initialPage: derivedPage,
    initialEvidenceIndex,
  });
}

/**
 * Get first page number from evidence refs, or null if none.
 */
export function getFirstPageFromEvidence(evidenceRefs: EvidenceRef[]): number | null {
  if (evidenceRefs.length === 0) return null;
  return evidenceRefs[0].page_number;
}






