/** PDF Navigation Context (Phase 8.6C).
 * 
 * Shared state for PDF viewer navigation from EvidenceDrawer and other components.
 */

"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export interface BboxHighlight {
  pageNumber: number;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  bboxSource: "pdf" | "image" | "none";
}

interface PdfNavigationContextType {
  currentPage: number | null;
  highlight: BboxHighlight | null;
  goToPage: (pageNumber: number) => void;
  highlightBbox: (highlight: BboxHighlight | null) => void;
  clearHighlight: () => void;
}

export const PdfNavigationContext = createContext<PdfNavigationContextType | undefined>(undefined);

export function PdfNavigationProvider({ children }: { children: ReactNode }) {
  const [currentPage, setCurrentPage] = useState<number | null>(null);
  const [highlight, setHighlight] = useState<BboxHighlight | null>(null);

  const goToPage = useCallback((pageNumber: number) => {
    setCurrentPage(pageNumber);
    // Clear highlight when navigating to new page
    setHighlight(null);
  }, []);

  const highlightBbox = useCallback((highlight: BboxHighlight | null) => {
    setHighlight(highlight);
  }, []);

  const clearHighlight = useCallback(() => {
    setHighlight(null);
  }, []);

  return (
    <PdfNavigationContext.Provider
      value={{
        currentPage,
        highlight,
        goToPage,
        highlightBbox,
        clearHighlight,
      }}
    >
      {children}
    </PdfNavigationContext.Provider>
  );
}

export function usePdfNavigation() {
  const context = useContext(PdfNavigationContext);
  if (!context) {
    throw new Error("usePdfNavigation must be used within PdfNavigationProvider");
  }
  return context;
}

