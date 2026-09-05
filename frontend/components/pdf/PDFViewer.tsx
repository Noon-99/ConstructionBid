/** PDF Viewer Component (Phase 8.6C).
 * 
 * Uses react-pdf to display PDF with page navigation and bbox highlighting.
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { usePdfNavigation } from "@/lib/pdf-navigation-context";
import type { BboxHighlight } from "@/lib/pdf-navigation-context";

// Set up PDF.js worker
if (typeof window !== "undefined") {
  // Use https:// CDN to avoid mixed content issues
  // For react-pdf v10 with pdfjs-dist v5.x, use unpkg.com with https://
  pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

interface PDFViewerProps {
  pdfUrl: string;
  className?: string;
}

export function PDFViewer({ pdfUrl, className = "" }: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [pageWidth, setPageWidth] = useState<number | null>(null);
  const [pageHeight, setPageHeight] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const { currentPage, highlight, goToPage } = usePdfNavigation();

  // Sync with navigation context
  useEffect(() => {
    if (currentPage !== null && currentPage !== pageNumber) {
      setPageNumber(currentPage);
    }
  }, [currentPage, pageNumber]);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setLoadError(null);
  };

  const onDocumentLoadError = (error: Error) => {
    console.error("PDF load error:", error);
    setLoadError(error.message || "Failed to load PDF. The file may not exist or may still be processing.");
  };

  const goToPrevPage = () => {
    if (pageNumber > 1) {
      const newPage = pageNumber - 1;
      setPageNumber(newPage);
      goToPage(newPage);
    }
  };

  const goToNextPage = () => {
    if (numPages && pageNumber < numPages) {
      const newPage = pageNumber + 1;
      setPageNumber(newPage);
      goToPage(newPage);
    }
  };

  const handleZoomIn = () => {
    setScale((prev) => Math.min(prev + 0.25, 3.0));
  };

  const handleZoomOut = () => {
    setScale((prev) => Math.max(prev - 0.25, 0.5));
  };

  // Calculate bbox overlay position (Phase 8.6C)
  const getBboxStyle = (bboxHighlight: BboxHighlight): React.CSSProperties | null => {
    if (!pageWidth || !pageHeight) return null;

    const { bbox, bboxSource } = bboxHighlight;
    let left: number, top: number, width: number, height: number;

    if (bboxSource === "pdf") {
      // Bbox is in PDF coordinate space (normalized 0-1)
      // Map directly to rendered page dimensions
      left = bbox.x0 * pageWidth;
      top = bbox.y0 * pageHeight;
      width = (bbox.x1 - bbox.x0) * pageWidth;
      height = (bbox.y1 - bbox.y0) * pageHeight;
    } else if (bboxSource === "image") {
      // Bbox is in image coordinate space (normalized 0-1 relative to image dimensions)
      // For now, assume image dimensions match rendered page (will be refined in Phase 8.7)
      // In Phase 8.7, we'll have actual image dimensions to map correctly
      left = bbox.x0 * pageWidth;
      top = bbox.y0 * pageHeight;
      width = (bbox.x1 - bbox.x0) * pageWidth;
      height = (bbox.y1 - bbox.y0) * pageHeight;
    } else {
      return null;
    }

    return {
      position: "absolute",
      left: `${left}px`,
      top: `${top}px`,
      width: `${width}px`,
      height: `${height}px`,
      border: "2px solid #3b82f6",
      backgroundColor: "rgba(59, 130, 246, 0.2)",
      pointerEvents: "none",
      zIndex: 10,
      borderRadius: "2px",
    };
  };

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Controls */}
      <div className="flex items-center justify-between p-2 border-b bg-white">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={goToPrevPage}
            disabled={pageNumber <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium">
            Page {pageNumber} {numPages ? `of ${numPages}` : ""}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={goToNextPage}
            disabled={!numPages || pageNumber >= numPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleZoomOut} disabled={scale <= 0.5}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">{Math.round(scale * 100)}%</span>
          <Button variant="outline" size="sm" onClick={handleZoomIn} disabled={scale >= 3.0}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* PDF Viewer */}
      <div className="flex-1 overflow-auto bg-gray-100 p-4 flex justify-center">
        {loadError ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="text-red-500 mb-2">Failed to load PDF</div>
            <div className="text-sm text-muted-foreground">{loadError}</div>
            <div className="text-xs text-muted-foreground mt-2">
              The PDF may still be processing. Please check back later.
            </div>
          </div>
        ) : (
          <div ref={pageRef} className="relative inline-block">
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={<div className="text-center p-8">Loading PDF...</div>}
              error={<div className="text-center p-8 text-red-500">Failed to load PDF</div>}
            >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              onLoadSuccess={(page) => {
                // Get actual rendered dimensions
                const viewport = page.getViewport({ scale });
                setPageWidth(viewport.width);
                setPageHeight(viewport.height);
              }}
              className="shadow-lg"
            />
          </Document>
          {/* Bbox Overlay */}
          {highlight &&
            highlight.pageNumber === pageNumber &&
            highlight.bboxSource !== "none" && (
              <div style={getBboxStyle(highlight) || {}} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

