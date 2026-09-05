"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Loader2, FileText } from "lucide-react";
import { api, ApiError } from "@/lib/api";

interface PdfButtonProps {
  projectId: string;
  generating: boolean;
  onGenerateStart: (jobId: string) => void;
  onGenerateEnd: () => void;
}

export function PdfButton({ projectId, generating, onGenerateStart, onGenerateEnd }: PdfButtonProps) {
  const [pdfAvailable, setPdfAvailable] = useState(false);
  const [checking, setChecking] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);

  // Check if PDF exists
  useEffect(() => {
    let isMounted = true;
    
    const checkPdf = async () => {
      try {
        // Try to fetch PDF (will 404 if not available)
        // Use HEAD request - 404s are expected and handled silently
        // Note: Browser console may still show 404 - this is expected behavior
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1";
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s timeout
        
        try {
          const response = await fetch(`${apiUrl}/projects/${projectId}/proposal.pdf`, {
            method: "HEAD",
            signal: controller.signal,
          });
          clearTimeout(timeoutId);
          
          if (isMounted) {
            setPdfAvailable(response.ok);
          }
        } catch (fetchError: any) {
          clearTimeout(timeoutId);
          // 404s and network errors are expected when PDF doesn't exist yet
          // Suppress console errors for expected 404s
          if (isMounted && fetchError.name !== "AbortError") {
            setPdfAvailable(false);
            // Don't log 404s - they're expected when PDF hasn't been generated yet
            if (fetchError.message && !fetchError.message.includes("404")) {
              // Only log non-404 errors
            }
          }
        }
      } catch (e) {
        // Silently handle any other errors (expected when PDF doesn't exist)
        if (isMounted) {
          setPdfAvailable(false);
        }
      } finally {
        if (isMounted) {
          setChecking(false);
        }
      }
    };

    checkPdf();
    
    return () => {
      isMounted = false;
    };
  }, [projectId]);

  // Poll job status if generating
  useEffect(() => {
    if (!generating || !jobId) return;

    const interval = setInterval(async () => {
      try {
        const status = await api.getJobStatus(jobId);
        if (status.status === "finished") {
          setPdfAvailable(true);
          onGenerateEnd();
          clearInterval(interval);
        } else if (status.status === "failed") {
          alert(`PDF generation failed: ${status.error || "Unknown error"}`);
          onGenerateEnd();
          clearInterval(interval);
        }
      } catch (e) {
        console.error("Error checking job status:", e);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [generating, jobId, onGenerateEnd]);

  const handleGenerate = async () => {
    try {
      const result = await api.generateProposalPdf(projectId);
      setJobId(result.job_id);
      onGenerateStart(result.job_id);
    } catch (err) {
      if (err instanceof ApiError) {
        alert(`Failed to generate PDF: ${err.message}`);
      } else {
        alert("Failed to generate PDF. Please try again.");
      }
      console.error("PDF generation error:", err);
    }
  };

  const handleDownload = () => {
    const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1"}/projects/${projectId}/proposal.pdf`;
    window.open(url, "_blank");
  };

  if (checking) {
    return null;
  }

  if (pdfAvailable) {
    return (
      <Button onClick={handleDownload} variant="default" size="sm">
        <Download className="h-4 w-4 mr-2" />
        Download Proposal PDF
      </Button>
    );
  }

  return (
    <Button
      onClick={handleGenerate}
      disabled={generating}
      variant="outline"
      size="sm"
    >
      {generating ? (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          Generating PDF...
        </>
      ) : (
        <>
          <FileText className="h-4 w-4 mr-2" />
          Generate Proposal PDF
        </>
      )}
    </Button>
  );
}

