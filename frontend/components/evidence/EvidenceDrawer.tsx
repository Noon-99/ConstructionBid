"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { FileText, ChevronDown, ChevronUp } from "lucide-react";
import type { EvidenceRef } from "@/lib/evidence-normalizer";
import { api } from "@/lib/api";
import { usePdfNavigationSafe } from "@/lib/use-pdf-navigation-safe";

interface EvidenceDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  evidence: EvidenceRef[];
  projectId: string; // Phase 8.6A: Required for page images
  initialPage?: number; // Phase 8.6B: 1-based page number to open at
  initialEvidenceIndex?: number; // Phase 8.6B: Optional index to focus/highlight
}

const SNIPPET_PREVIEW_LENGTH = 150;
const INITIAL_SNIPPET_LIMIT = 10;

export function EvidenceDrawer({
  open,
  onOpenChange,
  title,
  subtitle,
  evidence,
  projectId,
  initialPage,
  initialEvidenceIndex,
}: EvidenceDrawerProps) {
  const [expandedSnippets, setExpandedSnippets] = useState<Set<number>>(new Set());
  const [showAllSnippets, setShowAllSnippets] = useState(false);
  const [showAllEvidence, setShowAllEvidence] = useState(false); // Phase 8.6B: Show all evidence toggle
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [pages, setPages] = useState<Array<{ page_number: number; url: string }>>([]);
  const [loadingPages, setLoadingPages] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null); // Phase 8.6B: Highlight specific snippet
  const pdfNav = usePdfNavigationSafe(); // Phase 8.6C: PDF navigation (optional)

  // Debug: Log evidence prop whenever it changes
  useEffect(() => {
    console.log("[EvidenceDrawer] Received evidence prop:", {
      open,
      evidenceCount: evidence?.length || 0,
      evidence: evidence,
      projectId,
      initialPage,
      initialEvidenceIndex,
    });
  }, [open, evidence, projectId, initialPage, initialEvidenceIndex]);

  // Load pages when drawer opens (Phase 8.6A)
  useEffect(() => {
    if (open && projectId) {
      console.log("[EvidenceDrawer] Loading pages, evidence:", evidence);
      setLoadingPages(true);
      api
        .listPages(projectId)
        .then((data) => {
          // Get unique page numbers from evidence
          const evidencePages = Array.from(
            new Set(evidence.map((ref) => ref.page_number).filter((p) => p > 0))
          ).sort((a, b) => a - b);

          console.log("[EvidenceDrawer] Evidence pages extracted:", evidencePages, "from evidence:", evidence);

          if (data && data.pages && data.pages.length > 0) {
            // Use API pages if available
            console.log("[EvidenceDrawer] Using API pages:", data.pages.length);
            setPages(data.pages);
          } else if (evidencePages.length > 0) {
            // If API doesn't return pages, create page entries from evidence
            // This ensures pages referenced in evidence are always shown
            console.log("[EvidenceDrawer] Creating pages from evidence:", evidencePages);
            const pagesFromEvidence = evidencePages.map((pageNum) => ({
              page_number: pageNum,
              url: api.getPageImageUrl(projectId, pageNum),
            }));
            setPages(pagesFromEvidence);
          } else {
            console.warn("[EvidenceDrawer] No pages available from API or evidence");
            setPages([]);
          }

          // Select initial page: use initialPage prop, or first page from evidence
          let targetPage: number | undefined = initialPage;
          if (!targetPage && evidencePages.length > 0) {
            targetPage = evidencePages[0];
          } else if (!targetPage && data && data.pages && data.pages.length > 0) {
            targetPage = data.pages[0].page_number;
          }

          console.log("[EvidenceDrawer] Setting selectedPage to:", targetPage, "(initialPage:", initialPage, ", evidencePages[0]:", evidencePages[0], ")");
          if (targetPage) {
            setSelectedPage(targetPage);
            // Phase 8.6C: Navigate PDF viewer to this page (if available)
            if (pdfNav) {
              pdfNav.goToPage(targetPage);
            }
          } else {
            console.warn("[EvidenceDrawer] No targetPage found, selectedPage will be null");
          }
        })
        .catch((err) => {
          // If API fails, still create pages from evidence
          const evidencePages = Array.from(
            new Set(evidence.map((ref) => ref.page_number).filter((p) => p > 0))
          ).sort((a, b) => a - b);

          if (evidencePages.length > 0) {
            const pagesFromEvidence = evidencePages.map((pageNum) => ({
              page_number: pageNum,
              url: api.getPageImageUrl(projectId, pageNum),
            }));
            setPages(pagesFromEvidence);

            // Select first evidence page
            const targetPage = initialPage || evidencePages[0];
            if (targetPage) {
              setSelectedPage(targetPage);
              if (pdfNav) {
                pdfNav.goToPage(targetPage);
              }
            }
          } else {
            // Only log error if we couldn't create pages from evidence either
            console.error("Failed to load pages and no evidence pages available:", err);
          }
        })
        .finally(() => {
          setLoadingPages(false);
        });
    }
  }, [open, projectId, evidence, initialPage, pdfNav]);

  // Phase 8.6B: Highlight initial evidence index
  useEffect(() => {
    if (initialEvidenceIndex !== undefined && initialEvidenceIndex !== null) {
      setHighlightedIndex(initialEvidenceIndex);
      // Scroll to highlighted item after a brief delay
      setTimeout(() => {
        const element = document.getElementById(`evidence-snippet-${initialEvidenceIndex}`);
        if (element) {
          element.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 300);
      // Remove highlight after animation
      setTimeout(() => setHighlightedIndex(null), 2000);
      
      // Phase 8.6C: Highlight bbox in PDF viewer if available
      if (pdfNav) {
        const evidenceRef = evidence[initialEvidenceIndex];
        if (evidenceRef && evidenceRef.bbox && evidenceRef.bbox_source && evidenceRef.bbox_source !== "none") {
          pdfNav.highlightBbox({
            pageNumber: evidenceRef.page_number,
            bbox: evidenceRef.bbox,
            bboxSource: evidenceRef.bbox_source as "pdf" | "image",
          });
        }
      }
    }
  }, [initialEvidenceIndex, evidence, pdfNav]);

  // Debug: Log evidence when drawer opens
  useEffect(() => {
    if (open) {
      console.log("[EvidenceDrawer] Opened with evidence:", {
        count: evidence.length,
        evidence: evidence,
        projectId,
        title,
      });
    }
  }, [open, evidence.length, projectId, title]);

  const hasEvidence = evidence.length > 0;

  // Group evidence by page number
  const evidenceByPage = evidence.reduce((acc, ref) => {
    const page = ref.page_number;
    if (!acc[page]) {
      acc[page] = [];
    }
    acc[page].push(ref);
    return acc;
  }, {} as Record<number, EvidenceRef[]>);

  // Get evidence for selected page (Phase 8.6B: filter by page unless showAllEvidence is true)
  const displayedEvidence = showAllEvidence
    ? evidence
    : selectedPage
    ? evidenceByPage[selectedPage] || []
    : [];

  // Debug: Log displayedEvidence calculation
  useEffect(() => {
    if (open) {
      console.log("[EvidenceDrawer] displayedEvidence calculation:", {
        showAllEvidence,
        selectedPage,
        evidenceByPageKeys: Object.keys(evidenceByPage),
        evidenceByPageForSelected: selectedPage ? evidenceByPage[selectedPage] : null,
        displayedEvidenceCount: displayedEvidence.length,
        displayedEvidence: displayedEvidence,
      });
    }
  }, [open, showAllEvidence, selectedPage, displayedEvidence.length]);

  const toggleSnippet = (index: number) => {
    const newExpanded = new Set(expandedSnippets);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSnippets(newExpanded);
  };

  // Extract unique detail refs
  const detailRefs = Array.from(
    new Set(
      evidence.flatMap((ref) => ref.detail_refs || []).filter(Boolean)
    )
  );

  // Get page image URL
  const getPageImageUrl = (pageNumber: number) => {
    return api.getPageImageUrl(projectId, pageNumber);
  };

  // Render bbox overlay (Phase 8.6A)
  const renderBboxOverlay = (ref: EvidenceRef) => {
    if (!ref.bbox) return null;

    const { x0, y0, x1, y1 } = ref.bbox;
    // Assume normalized coordinates (0..1) for now
    const left = `${x0 * 100}%`;
    const top = `${y0 * 100}%`;
    const width = `${(x1 - x0) * 100}%`;
    const height = `${(y1 - y0) * 100}%`;

    return (
      <div
        className="absolute border-2 border-blue-500 bg-blue-500/20 pointer-events-none z-10"
        style={{
          left,
          top,
          width,
          height,
        }}
      />
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-6xl overflow-hidden flex flex-col p-0">
        <SheetHeader className="px-6 pt-6 pb-4 border-b">
          <SheetTitle className="text-xl font-semibold">{title}</SheetTitle>
          {subtitle && (
            <SheetDescription className="text-sm text-muted-foreground">
              {subtitle}
            </SheetDescription>
          )}
        </SheetHeader>

        {!hasEvidence ? (
          <div className="flex flex-col items-center justify-center py-12 text-center px-6">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-sm font-medium mb-2">No evidence linked for this item yet.</p>
            <p className="text-xs text-muted-foreground">
              {evidence.length === 0
                ? "Evidence may not have been extracted yet. The pipeline may still be processing."
                : "Evidence data is not available for this item."}
            </p>
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* Left: Page Thumbnails (20%) */}
            <div className="w-[20%] border-r bg-muted/30 overflow-y-auto">
              <div className="p-4 space-y-2">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-3">
                  Pages
                </h3>
                {loadingPages ? (
                  <div className="text-xs text-muted-foreground">Loading pages...</div>
                ) : pages.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No pages available</div>
                ) : (
                  pages.map((page) => {
                    const isSelected = selectedPage === page.page_number;
                    const hasEvidence = evidenceByPage[page.page_number]?.length > 0;
                    return (
                      <button
                        key={page.page_number}
                        onClick={() => {
                          setSelectedPage(page.page_number);
                          // Phase 8.6C: Navigate PDF viewer to this page (if available)
                          if (pdfNav) {
                            pdfNav.goToPage(page.page_number);
                          }
                        }}
                        className={`w-full aspect-[3/4] relative rounded border-2 overflow-hidden transition-all ${
                          isSelected
                            ? "border-primary ring-2 ring-primary/20"
                            : "border-border hover:border-primary/50"
                        } ${hasEvidence ? "bg-background" : "bg-muted opacity-50"}`}
                      >
                        <img
                          src={getPageImageUrl(page.page_number)}
                          alt={`Page ${page.page_number}`}
                          className="w-full h-full object-contain"
                          loading="lazy"
                        />
                        <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white text-xs px-2 py-1 text-center">
                          {page.page_number}
                        </div>
                        {hasEvidence && (
                          <div className="absolute top-1 right-1">
                            <Badge variant="secondary" className="text-xs h-5 px-1.5">
                              {evidenceByPage[page.page_number].length}
                            </Badge>
                          </div>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Center: Main Page Image Viewer (55-60%) */}
            <div className="flex-1 bg-gray-100 overflow-auto flex flex-col">
              {selectedPage ? (
                <div className="flex-1 flex items-center justify-center p-4">
                  <div className="relative max-w-full max-h-full">
                    <img
                      src={getPageImageUrl(selectedPage)}
                      alt={`Page ${selectedPage}`}
                      className="max-w-full max-h-full object-contain shadow-lg"
                      onError={(e) => {
                        // If image fails to load, show placeholder
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        const placeholder = target.parentElement?.querySelector('.page-placeholder');
                        if (placeholder) {
                          (placeholder as HTMLElement).style.display = 'flex';
                        }
                      }}
                    />
                    <div className="page-placeholder hidden flex-col items-center justify-center text-muted-foreground">
                      <FileText className="h-12 w-12 mb-2 opacity-50" />
                      <p className="text-sm">Page {selectedPage}</p>
                      <p className="text-xs mt-1">Image not available</p>
                    </div>
                    {/* Bbox overlays for selected page evidence */}
                    {displayedEvidence.map((ref, idx) => renderBboxOverlay(ref))}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground">
                  Select a page to view
                </div>
              )}
            </div>

            {/* Right: Evidence List (20-25%) */}
            <div className="w-[25%] border-l bg-background overflow-y-auto">
              <ScrollArea className="h-full">
                <div className="p-4 space-y-4">
                  {/* Details Referenced */}
                  {detailRefs.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold mb-2 flex items-center gap-2">
                        <FileText className="h-3 w-3" />
                        Details Referenced
                      </h3>
                      <div className="flex flex-wrap gap-1.5">
                        {detailRefs.map((detailRef, idx) => (
                          <Badge
                            key={idx}
                            variant="secondary"
                            className="font-mono text-xs"
                          >
                            {detailRef}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  <Separator />

                  {/* Evidence Snippets (Phase 8.6B: Show all or filtered by page) */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-xs font-semibold">
                        {showAllEvidence
                          ? `Evidence (${evidence.length} total)`
                          : selectedPage
                          ? `Evidence (Page ${selectedPage})`
                          : "Evidence"}
                      </h3>
                      <div className="flex items-center gap-2">
                        {/* Show all evidence toggle (Phase 8.6B) */}
                        {evidence.length > 0 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowAllEvidence(!showAllEvidence)}
                            className="text-xs h-6"
                          >
                            {showAllEvidence ? "This Page" : "All Pages"}
                          </Button>
                        )}
                        {displayedEvidence.length > INITIAL_SNIPPET_LIMIT && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowAllSnippets(!showAllSnippets)}
                            className="text-xs h-6"
                          >
                            {showAllSnippets ? (
                              <>
                                <ChevronUp className="h-3 w-3 mr-1" />
                                Less
                              </>
                            ) : (
                              <>
                                <ChevronDown className="h-3 w-3 mr-1" />
                                All
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                    </div>

                    {displayedEvidence.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        {showAllEvidence
                          ? "No evidence snippets available."
                          : selectedPage
                          ? `No evidence snippets for page ${selectedPage}.`
                          : "Select a page to view evidence."}
                      </p>
                    ) : (
                      <Accordion type="multiple" className="w-full">
                        {(showAllSnippets
                          ? displayedEvidence
                          : displayedEvidence.slice(0, INITIAL_SNIPPET_LIMIT)
                        ).map((ref, idx) => {
                          const globalIndex = evidence.findIndex((e) => e === ref);
                          const isHighlighted = highlightedIndex === globalIndex;
                          const isExpanded = expandedSnippets.has(idx);
                          const snippet = ref.snippet || "";
                          const isLong = snippet.length > SNIPPET_PREVIEW_LENGTH;
                          const displaySnippet =
                            isLong && !isExpanded
                              ? `${snippet.substring(0, SNIPPET_PREVIEW_LENGTH)}...`
                              : snippet;
                          const hasBbox = ref.bbox !== null && ref.bbox !== undefined;

                          const handleSnippetClick = () => {
                            // Keep EvidenceDrawer UI in sync with PDF navigation
                            if (ref.page_number && ref.page_number !== selectedPage) {
                              setSelectedPage(ref.page_number);
                            }

                            // Phase 8.6C: Navigate PDF to this snippet's page and highlight bbox (if available)
                            if (pdfNav) {
                              pdfNav.goToPage(ref.page_number);
                              if (ref.bbox && ref.bbox_source && ref.bbox_source !== "none") {
                                pdfNav.highlightBbox({
                                  pageNumber: ref.page_number,
                                  bbox: ref.bbox,
                                  bboxSource: ref.bbox_source as "pdf" | "image",
                                });
                              }
                            }
                          };

                            return (
                              <AccordionItem
                                key={idx}
                                value={`snippet-${idx}`}
                                id={`evidence-snippet-${globalIndex}`}
                                className={isHighlighted ? "animate-pulse bg-blue-50 dark:bg-blue-950/20" : ""}
                              >
                                <AccordionTrigger className="py-2" onClick={handleSnippetClick}>
                                  <div className="flex items-center gap-1.5 flex-1 text-left text-xs">
                                    {ref.sheet_id && (
                                      <Badge variant="outline" className="text-xs h-4 px-1">
                                        {ref.sheet_id}
                                      </Badge>
                                    )}
                                    {ref.location_type && (
                                      <Badge variant="secondary" className="text-xs h-4 px-1">
                                        {ref.location_type}
                                      </Badge>
                                    )}
                                    {!hasBbox && (
                                      <span className="text-muted-foreground text-[10px]">
                                        No region box
                                      </span>
                                    )}
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-2 pt-2">
                                    {ref.sheet_title && (
                                      <p className="text-xs text-muted-foreground">
                                        <span className="font-medium">Sheet:</span> {ref.sheet_title}
                                      </p>
                                    )}
                                    <p
                                      className={`text-xs font-mono bg-muted p-2 rounded border ${
                                        isLong ? "cursor-pointer" : ""
                                      }`}
                                      onClick={() => isLong && toggleSnippet(idx)}
                                    >
                                      {displaySnippet}
                                    </p>
                                    {!hasBbox && (
                                      <p className="text-[10px] text-muted-foreground italic">
                                        No region box available yet
                                      </p>
                                    )}
                                    {isLong && (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => toggleSnippet(idx)}
                                        className="text-xs h-6"
                                      >
                                        {isExpanded ? "Show Less" : "Show More"}
                                      </Button>
                                    )}
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            );
                          })}
                        </Accordion>
                      )}
                    </div>
                </div>
              </ScrollArea>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
