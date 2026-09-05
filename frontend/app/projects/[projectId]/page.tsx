"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, ApiError, ProjectSummary } from "@/lib/api";
import { AlertCircle, CheckCircle2, XCircle, Loader2, FileText, Briefcase } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import Link from "next/link";
import { OverviewTab } from "@/components/project/OverviewTab";
import { BidTab } from "@/components/project/BidTab";
import { ReviewTab } from "@/components/project/ReviewTab";
import { EvidenceTab } from "@/components/project/EvidenceTab";
import { Model3DTab } from "@/components/project/Model3DTab";
import { MetricsTab } from "@/components/project/MetricsTab";
import { ProposalTab } from "@/components/project/ProposalTab";
import { TradePackagesTab } from "@/components/project/TradePackagesTab";
import { TrustReportTab } from "@/components/project/TrustReportTab";
import { TradeAssembliesTab } from "@/components/project/TradeAssembliesTab";
import { GeneralConditionsTab } from "@/components/project/GeneralConditionsTab";
import { PdfButton } from "@/components/project/PdfButton";
import { PdfNavigationProvider } from "@/lib/pdf-navigation-context";
import dynamic from "next/dynamic";
import { WalkthroughMode } from "@/components/project/WalkthroughMode";

// PDFViewer uses DOMMatrix which is not available in SSR - load client-only
const PDFViewer = dynamic(() => import("@/components/pdf/PDFViewer").then(mod => ({ default: mod.PDFViewer })), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-96">Loading PDF viewer...</div>
});
import { Button } from "@/components/ui/button";
import { BookOpen } from "lucide-react";

export default function ProjectPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [pdfGenerating, setPdfGenerating] = useState(false);
  const [pdfJobId, setPdfJobId] = useState<string | null>(null);
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);
  const [contractorMode, setContractorMode] = useState(false); // Phase 10.13A
  const [pageIndexStatus, setPageIndexStatus] = useState<{
    status: "not_started" | "running" | "succeeded" | "failed" | "unknown" | "queued";
    progress?: {
      total_pages: number;
      completed_pages: number;
      cached_pages: number;
      failed_pages: number;
      updated_at: string;
    } | null;
  } | null>(null);
  const [pageIndexPolling, setPageIndexPolling] = useState(false);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<Awaited<ReturnType<typeof api.getProjectStatus>> | null>(null);

  const handleRunPipeline = async () => {
    // Prevent double-clicks
    if (pipelineRunning || summary?.status === "running") {
      console.log("Pipeline already running, ignoring click");
      return;
    }
    try {
      console.log("handleRunPipeline called, status:", summary?.status);
      setError(null); // Clear any previous errors
      setPipelineStatus(null); // Reset pipeline status to show fresh progress from 0%
      setPipelineRunning(true); // Set running flag immediately so polling starts
      console.log("Starting pipeline for project:", projectId);
      
      // Call API
      const result = await api.runProject(projectId);
      console.log("Pipeline started successfully:", result);

      if (result.status) {
        setSummary(prev => (prev ? { ...prev, status: result.status as ProjectSummary["status"] } : prev));
      }
      
      // Immediately refresh status
      await loadSummary();
      await loadPipelineStatus();
      
      // The useEffect will continue polling
    } catch (err) {
      console.error("Failed to start pipeline:", err);
      setPipelineRunning(false); // Clear on error
      let errorMessage = "Failed to start pipeline";
      if (err instanceof ApiError) {
        if (err.status === 503) {
          errorMessage = "Redis or Worker is not running.\n\n" +
            "To fix:\n" +
            "1. Start Redis: docker run -d -p 6379:6379 --name redis-construction redis\n" +
            "2. Start Worker: ./start-worker.sh (or python -m app.workers.worker)\n\n" +
            "See WORKER_SETUP.md for details.";
        } else if (err.status === 400) {
          errorMessage = err.message || "Invalid request. Please check the project exists.";
        } else if (err.status === 500 && err.message?.includes("already being processed")) {
          errorMessage = "Pipeline is already running for this project. If stuck, clear the lock:\n\n" +
            "python3 -c \"from redis import Redis; r = Redis.from_url('redis://localhost:6379/0'); r.delete('pipeline:lock:" + projectId + "')\"";
        } else {
          errorMessage = err.message || `Server error (${err.status})`;
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setPipelineRunning(false);
    }
  };

  const loadSummary = async () => {
    try {
      // Add timeout to prevent infinite loading
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error("Request timeout after 10 seconds")), 10000);
      });
      
      const data = await Promise.race([
        api.getProjectSummary(projectId),
        timeoutPromise,
      ]) as ProjectSummary;
      
      setSummary(data);
      setError(null);
      
      // Poll if status indicates we are pending or running
      if ((data.status === "uploaded" || data.status === "running" || data.status === "not_started" || data.status === "queued") && !polling) {
        setPolling(true);
        // Also trigger pipeline if status is "uploaded" (in case auto-trigger didn't work)
        if (data.status === "uploaded") {
          try {
            await api.runProject(projectId);
            console.log("Auto-triggered pipeline for uploaded project");
          } catch (err) {
            console.warn("Failed to auto-trigger pipeline:", err);
          }
        }
        const interval = setInterval(async () => {
          try {
            const updated = await api.getProjectSummary(projectId);
            setSummary(updated);
            // Also load pipeline status for progress display
            loadPipelineStatus();
            // Keep polling until status is "succeeded", "failed", or "completed"
            if (updated.status === "succeeded" || updated.status === "failed" || updated.status === "completed") {
              clearInterval(interval);
              setPolling(false);
              setPipelineRunning(false);
            }
          } catch (err) {
            console.error("Polling error:", err);
            clearInterval(interval);
            setPolling(false);
          }
        }, 2000); // Poll every 2 seconds for faster updates
        
        return () => clearInterval(interval);
      }
    } catch (err) {
      console.error("Load error:", err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error && err.message.includes("timeout")) {
        setError("Backend is not responding. Please check if the server is running at http://localhost:8000");
      } else {
        setError("Failed to load project. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const loadPageIndexStatus = async () => {
    try {
      const status = await api.getPageIndexJobStatus(projectId);
      setPageIndexStatus(status);

      // Poll if status is "running"
      if ((status.status === "running" || status.status === "queued") && !pageIndexPolling) {
        setPageIndexPolling(true);
        const interval = setInterval(async () => {
          try {
            const updated = await api.getPageIndexJobStatus(projectId);
            setPageIndexStatus(updated);
            if (updated.status !== "running" && updated.status !== "queued") {
              clearInterval(interval);
              setPageIndexPolling(false);
              // Reload summary to reflect page index completion
              loadSummary();
            }
          } catch (err) {
            console.error("Page index polling error:", err);
            clearInterval(interval);
            setPageIndexPolling(false);
          }
        }, 2500); // Poll every 2.5 seconds

        return () => clearInterval(interval);
      } else if (status.status !== "running" && status.status !== "queued") {
        setPageIndexPolling(false);
      }
    } catch (err) {
      console.error("Failed to load page index status:", err);
      // Don't show error - page indexing might not be started yet
    }
  };

  const loadPipelineStatus = async () => {
    try {
      const status = await api.getProjectStatus(projectId);
      setPipelineStatus(status);
    } catch (err) {
      console.error("Failed to load pipeline status:", err);
      // Don't show error - status might not be available yet
    }
  };

  useEffect(() => {
    // Load initial data
    loadSummary();
    loadPageIndexStatus();
    loadPipelineStatus();
    
    // Don't auto-trigger - let user manually trigger via button
    // Only set polling/running if status is actually "running"
    const checkStatus = async () => {
      try {
        const initialSummary = await api.getProjectSummary(projectId).catch(() => null);
        if (initialSummary && initialSummary.status === "running") {
          setPolling(true);
          setPipelineRunning(true);
        } else {
          setPolling(false);
          setPipelineRunning(false);
        }
      } catch (err) {
        console.error("Failed to check initial status:", err);
        setPolling(false);
        setPipelineRunning(false);
      }
    };
    checkStatus();
  }, [projectId]);

  // Poll pipeline status when running
  useEffect(() => {
    // Check if pipeline is actually done (all stages completed)
    const isDone = pipelineStatus && pipelineStatus.stages && pipelineStatus.stages.length > 0 && 
                   pipelineStatus.stages.every(s => s.status === "succeeded" || s.status === "failed");
    const summaryTerminal = summary?.status === "failed" || summary?.status === "succeeded" || summary?.status === "completed";
    
    // ALWAYS clear running flag if pipeline is done (stages finished)
    if (isDone) {
      setPipelineRunning(false);
      setPolling(false);
      return;
    }

    // Only stop early on terminal summary if we aren't actively running a new job
    if (!pipelineRunning && summaryTerminal) {
      setPolling(false);
      return;
    }
    
    // Poll if status is "running" OR if we just started a job (pipelineRunning is true) OR if pipelineStatus shows running
    const shouldPoll = 
      summary?.status === "running" || 
      (pipelineStatus && pipelineStatus.status === "running") ||
      pipelineRunning;
    
    if (shouldPoll) {
      // Set pipeline running flag to show progress UI
      setPipelineRunning(true);
      setPolling(true);
      
      // Poll immediately, then set up interval
      loadPipelineStatus();
      loadSummary();
      loadPageIndexStatus();
      
      const interval = setInterval(() => {
        loadPipelineStatus();
        loadSummary();
        loadPageIndexStatus(); // Also poll page index status
      }, 1000); // Poll every 1 second for real-time updates
      return () => clearInterval(interval);
    } else {
      // Stop polling and clear running flag when not running
      setPipelineRunning(false);
      setPolling(false);
    }
  }, [summary?.status, pipelineRunning, pipelineStatus?.status, pipelineStatus?.stages, projectId]);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="whitespace-pre-line">{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>Project not found</AlertDescription>
        </Alert>
      </div>
    );
  }

  const statusIcon = {
    succeeded: <CheckCircle2 className="h-5 w-5 text-green-500" />,
    completed: <CheckCircle2 className="h-5 w-5 text-blue-500" />,
    running: <Loader2 className="h-5 w-5 animate-spin text-blue-500" />,
    failed: <XCircle className="h-5 w-5 text-red-500" />,
    queued: <Loader2 className="h-5 w-5 animate-spin text-amber-500" />,
    uploaded: <AlertCircle className="h-5 w-5 text-gray-400" />,
    not_started: <AlertCircle className="h-5 w-5 text-gray-400" />,
  }[summary.status] || <AlertCircle className="h-5 w-5 text-gray-500" />;

  const pipelineCardState: "running" | "queued" | "completed" | null = (() => {
    if (pipelineStatus?.status === "running") {
      return "running";
    }
    if (pipelineStatus?.status === "succeeded") {
      return "completed";
    }
    if (
      pipelineRunning ||
      summary?.status === "queued" ||
      summary?.status === "uploaded" ||
      summary?.status === "running"
    ) {
      return "queued";
    }
    return null;
  })();

  const totalStages = pipelineStatus?.stages?.length ?? 0;
  const completedStages = pipelineStatus?.stages?.filter(
    s => s.status === "succeeded" || s.status === "failed"
  ).length ?? 0;
  const basePercent = totalStages > 0 ? Math.round((completedStages / totalStages) * 100) : 0;
  const progressBarPercent = pipelineCardState === "completed"
    ? 100
    : totalStages > 0
      ? basePercent
      : pipelineCardState === "queued"
        ? 5
        : basePercent;

  const pageIndexPercent = pageIndexStatus?.progress && pageIndexStatus.progress.total_pages > 0
    ? Math.round((pageIndexStatus.progress.completed_pages / pageIndexStatus.progress.total_pages) * 100)
    : 0;

  return (
    <PdfNavigationProvider>
      <div className="min-h-screen bg-gray-50">
        <div className="container mx-auto px-4 py-8 space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="whitespace-pre-line">{error}</AlertDescription>
            </Alert>
          )}

          <header className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold">Project: {projectId}</h1>
            {statusIcon}
            <Badge variant={summary.status === "succeeded" ? "default" : "secondary"}>{summary.status}</Badge>
            {polling && (
              <Badge variant="outline" className="animate-pulse">
                Polling...
              </Badge>
            )}
            {summary.status === "succeeded" && (
              <>
                <Link href={`/projects/${projectId}/proposal`}>
                  <Badge variant="outline" className="cursor-pointer hover:bg-gray-100">
                    <FileText className="h-3 w-3 mr-1" />
                    View Proposal
                  </Badge>
                </Link>
                <PdfButton
                  projectId={projectId}
                  generating={pdfGenerating}
                  onGenerateStart={(jobId) => {
                    setPdfGenerating(true);
                    setPdfJobId(jobId);
                  }}
                  onGenerateEnd={() => setPdfGenerating(false)}
                />
                <Button variant="outline" size="sm" onClick={() => setWalkthroughOpen(true)}>
                  <BookOpen className="h-3 w-3 mr-1" />
                  Walkthrough
                </Button>
              </>
            )}
            <Button
              variant="default"
              size="sm"
              onClick={async (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!pipelineRunning && summary.status !== "running") {
                  await handleRunPipeline();
                }
              }}
              disabled={pipelineRunning || summary?.status === "running"}
            >
              {pipelineRunning || summary.status === "running" ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Running...
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  Re-run Pipeline
                </span>
              )}
            </Button>
          </header>

          <div className="space-y-2">
            {!contractorMode && summary.last_updated && (
              <p className="text-sm text-gray-500">
                Last updated: {new Date(summary.last_updated).toLocaleString()}
              </p>
            )}

            <div className="flex items-center gap-2">
              <Switch id="contractor-mode" checked={contractorMode} onCheckedChange={setContractorMode} />
              <Label htmlFor="contractor-mode" className="flex items-center gap-2 cursor-pointer">
                <Briefcase className="h-4 w-4" />
                <span className="text-sm font-medium">Contractor Mode</span>
              </Label>
            </div>
          </div>

          {pipelineCardState && (
            <Card className="border-green-200 bg-green-50">
              <CardContent className="pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {pipelineCardState === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin text-green-600" />
                    )}
                    <span className="font-medium text-green-900">
                      {pipelineCardState === "completed"
                        ? "Pipeline Complete"
                        : pipelineCardState === "running"
                        ? "Pipeline Running"
                        : "Waiting for worker…"}
                      {pipelineCardState !== "queued" && pipelineStatus?.current_stage && (
                        <span className="ml-2 text-sm font-normal text-green-700">
                          • {pipelineStatus.current_stage.replace(/_/g, " ").replace(/stage /g, "").replace(/^\d+\.?\d*\s*/, "")}
                        </span>
                      )}
                    </span>
                  </div>
                  {pipelineCardState === "running" && (
                    <Badge variant="outline" className="border-green-400 text-green-700">
                      Active
                    </Badge>
                  )}
                </div>
                <div className="w-full bg-green-200 rounded-full h-2.5">
                  <div
                    className="bg-green-600 h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${Math.max(0, Math.min(100, progressBarPercent))}%` }}
                  />
                </div>
                {totalStages > 0 ? (
                  <div className="space-y-2">
                    {pipelineStatus?.stages?.map((stage, index) => {
                      const isRunning = stage.status === "running";
                      const isCompleted = stage.status === "succeeded";
                      const isFailed = stage.status === "failed";
                      const stageNumber = `${index + 1}.`;
                      const stageLabel = stage.stage_name
                        .replace(/_/g, " ")
                        .replace(/stage /gi, "")
                        .replace(/^\d+\.?\d*\s*/, "");
                      const duration = stage.duration_seconds
                        ? `${(stage.duration_seconds / 60).toFixed(1)}m`
                        : stage.elapsed_seconds
                        ? `${Math.max(1, Math.round(stage.elapsed_seconds / 60))}m est.`
                        : null;

                      return (
                        <div
                          key={stage.stage_name}
                          className={`flex items-center justify-between text-sm rounded-md px-3 py-2 ${
                            isRunning
                              ? "bg-green-100 text-green-900 border border-green-200"
                              : isCompleted
                              ? "bg-white text-green-800 border border-green-100"
                              : isFailed
                              ? "bg-red-50 text-red-700 border border-red-100"
                              : "bg-white text-gray-600 border border-transparent"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-xs text-gray-500">{stageNumber}</span>
                            <span className="font-medium">
                              {stageLabel}
                              {isRunning && <span className="ml-2 text-xs text-green-700">Running…</span>}
                              {isCompleted && <span className="ml-2 text-xs text-green-600">Done</span>}
                              {isFailed && <span className="ml-2 text-xs text-red-600">Failed</span>}
                            </span>
                          </div>
                          {duration && (
                            <span className="text-gray-500 text-right flex-shrink-0 ml-2">{duration}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-green-700">Preparing pipeline…</div>
                )}
              </CardContent>
            </Card>
          )}

          {pageIndexStatus && (pageIndexStatus.status === "running" || pageIndexStatus.status === "queued") && pageIndexStatus.progress && (
            <Card className="border-blue-200 bg-blue-50">
              <CardContent className="pt-4 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-blue-900">
                    Indexing pages: {pageIndexStatus.progress.completed_pages} / {pageIndexStatus.progress.total_pages}
                  </span>
                  {pageIndexPolling && <Loader2 className="h-4 w-4 animate-spin text-blue-600" />}
                </div>
                <div className="w-full bg-blue-200 rounded-full h-2.5">
                  <div
                    className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${pageIndexPercent}%` }}
                  />
                </div>
                <div className="flex flex-wrap items-center gap-4 text-xs text-blue-700">
                  <span>Completed: {pageIndexStatus.progress.completed_pages}</span>
                  {pageIndexStatus.progress.cached_pages > 0 && <span>Cached: {pageIndexStatus.progress.cached_pages}</span>}
                  {pageIndexStatus.progress.failed_pages > 0 && (
                    <span className="text-red-600">Failed: {pageIndexStatus.progress.failed_pages}</span>
                  )}
                  {pageIndexStatus.progress.updated_at && (
                    <span className="ml-auto text-gray-500">
                      Updated: {new Date(pageIndexStatus.progress.updated_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {summary?.status === "uploaded" && !pipelineStatus && !pageIndexStatus && (
            <Card className="border-green-200 bg-green-50">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-green-600" />
                  <span className="font-medium text-green-900">Starting pipeline...</span>
                </div>
              </CardContent>
            </Card>
          )}

          <Tabs defaultValue="overview" className="space-y-4">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="bid">{contractorMode ? "Bid Package" : "Bid"}</TabsTrigger>
              {!contractorMode && <TabsTrigger value="proposal">Proposal</TabsTrigger>}
              {!contractorMode && <TabsTrigger value="review">Review</TabsTrigger>}
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="3d">3D Model</TabsTrigger>
              <TabsTrigger value="trade-assemblies">Assemblies</TabsTrigger>
              <TabsTrigger value="general-conditions">General Conditions</TabsTrigger>
              <TabsTrigger value="trade-packages">Trade Packages</TabsTrigger>
              <TabsTrigger value="trust">Trust</TabsTrigger>
              <TabsTrigger value="pdf">PDF</TabsTrigger>
              {!contractorMode && <TabsTrigger value="metrics">Metrics</TabsTrigger>}
            </TabsList>

            <TabsContent value="overview">
              <OverviewTab projectId={projectId} summary={summary} contractorMode={contractorMode} />
            </TabsContent>

            <TabsContent value="bid">
              <BidTab projectId={projectId} />
            </TabsContent>

            {!contractorMode && (
              <TabsContent value="proposal">
                <ProposalTab projectId={projectId} />
              </TabsContent>
            )}

            {!contractorMode && (
              <TabsContent value="review">
                <ReviewTab projectId={projectId} />
              </TabsContent>
            )}

            <TabsContent value="evidence">
              <EvidenceTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="3d">
              <Model3DTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="trade-assemblies">
              <TradeAssembliesTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="general-conditions">
              <GeneralConditionsTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="trade-packages">
              <TradePackagesTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="trust">
              <TrustReportTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="pdf">
              <div className="h-[calc(100vh-200px)]">
                <PDFViewer pdfUrl={api.getSourcePdfUrl(projectId)} />
              </div>
            </TabsContent>

            {!contractorMode && (
              <TabsContent value="metrics">
                <MetricsTab projectId={projectId} />
              </TabsContent>
            )}
          </Tabs>

          {walkthroughOpen && summary && (
            <WalkthroughMode
              summary={summary}
              totalBid={summary.total_cost}
              projectId={projectId}
              onClose={() => setWalkthroughOpen(false)}
              onHighlightTab={(tab) => {
                const tabElement = document.querySelector(`[value="${tab}"]`);
                if (tabElement) {
                  (tabElement as HTMLElement).click();
                }
              }}
            />
          )}
        </div>
      </div>
    </PdfNavigationProvider>
  );
}
