"use client";

import { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Loader2, Download, FileText, AlertCircle } from "lucide-react";
import Link from "next/link";

interface ProposalTabProps {
  projectId: string;
}

interface ContractorBid {
  region_resolution?: {
    region_id: string;
    confidence: number;
    evidence?: string;
  };
}

export function ProposalTab({ projectId }: ProposalTabProps) {
  const [contractorBid, setContractorBid] = useState<ContractorBid | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [pdfExists, setPdfExists] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {

        // Try to load contractor bid for profile info
        try {
          const bid = await api.getContractorBid(projectId);
          setContractorBid(bid);
        } catch (err) {
          // Contractor bid might not exist
          setContractorBid(null);
        }

        // Check if contractor PDF exists (404s are expected)
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5000);
          try {
            const pdfResponse = await fetch(
              `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`,
              { method: "HEAD", signal: controller.signal }
            );
            clearTimeout(timeoutId);
            setPdfExists(pdfResponse.ok);
          } catch (fetchErr: any) {
            clearTimeout(timeoutId);
            // 404s and AbortErrors are expected when PDF doesn't exist yet - handle silently
            // Suppress console errors for expected 404s
            if (fetchErr.name !== "AbortError" && fetchErr.message && !fetchErr.message.includes("404")) {
              // Only log unexpected errors (not 404s or aborts)
            }
            setPdfExists(false);
          }
        } catch {
          // Silently handle any outer errors
          setPdfExists(false);
        }

        setError(null);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load proposal data.");
        }
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId]);

  const handleGeneratePdf = async () => {
    setGeneratingPdf(true);
    try {
      await api.generateContractorProposalPdf(projectId);
      // Poll for PDF existence (suppress 404 errors - they're expected)
      setTimeout(() => {
        const checkPdf = async () => {
          try {
            const response = await fetch(
              `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`,
              { method: "HEAD" }
            );
            setPdfExists(response.ok);
          } catch (err: any) {
            // Suppress 404 errors - PDF may not exist yet
            if (err.message && !err.message.includes("404")) {
              // Only log non-404 errors if needed
            }
            setPdfExists(false);
          }
        };
        checkPdf();
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to generate PDF.");
      }
    } finally {
      setGeneratingPdf(false);
    }
  };

  const handleDownloadPdf = () => {
    const url = `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/v1"}/projects/${projectId}/contractor_proposal.pdf`;
    window.open(url, "_blank");
  };

  // Extract profile ID from region_resolution or use default
  const profileDisplay = contractorBid?.region_resolution
    ? (() => {
        const regionId = contractorBid.region_resolution.region_id;
        const profileMap: Record<string, string> = {
          nyc: "NYC v1",
          nj: "NJ v1",
          tx: "TX v1",
          us_default: "US Default v1",
        };
        return profileMap[regionId] || `${regionId.toUpperCase()} v1`;
      })()
    : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <Alert>
        <FileText className="h-4 w-4" />
        <AlertDescription>
          <div className="space-y-2">
            <p>
              The full proposal view with contractor-style sections is available on the dedicated proposal page.
            </p>
            <div>
              <Link href={`/projects/${projectId}/proposal`}>
                <Button variant="default">
                  <FileText className="h-4 w-4 mr-2" />
                  View Full Proposal
                </Button>
              </Link>
            </div>
          </div>
        </AlertDescription>
      </Alert>

      {/* Header with Profile Info and Actions */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Contractor Proposal</CardTitle>
            <div className="flex items-center gap-2">
              {profileDisplay && (
                <Badge variant="secondary" className="text-xs">
                  Profile: {profileDisplay}
                </Badge>
              )}
              {contractorBid?.region_resolution && (
                <Badge variant="outline" className="text-xs">
                  Region: {contractorBid.region_resolution.region_id.toUpperCase()} (
                  {(contractorBid.region_resolution.confidence * 100).toFixed(0)}%)
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {pdfExists ? (
              <Button size="sm" variant="default" onClick={handleDownloadPdf}>
                <Download className="h-4 w-4 mr-2" />
                Download Proposal PDF
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={handleGeneratePdf}
                disabled={generatingPdf}
              >
                {generatingPdf ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Generating PDF...
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4 mr-2" />
                    Generate Proposal PDF
                  </>
                )}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

