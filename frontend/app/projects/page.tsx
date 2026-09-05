"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Upload,
  Download,
  FileText,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Filter,
  ArrowUpDown,
} from "lucide-react";
import { api, ApiError, type ProjectSummary } from "@/lib/api";

type ProjectListItem = ProjectSummary & {
  proposal_pdf_available?: boolean;
};

type FilterType = "all" | "bid_ready" | "needs_review";
type SortField = "cost" | "readiness_score" | "geometry_quality";
type SortDirection = "asc" | "desc";

export default function ProjectsDashboard() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<FilterType>("all");
  const [sortField, setSortField] = useState<SortField>("cost");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [exporting, setExporting] = useState(false);
  const [failIfMissingPdf, setFailIfMissingPdf] = useState(false);

  // Load project IDs from localStorage
  useEffect(() => {
    const loadProjects = async () => {
      try {
        const stored = localStorage.getItem("recentProjects");
        const projectIds: string[] = stored ? JSON.parse(stored) : [];

        if (projectIds.length === 0) {
          setLoading(false);
          return;
        }

        // Fetch summaries with concurrency limit
        const concurrencyLimit = 5;
        const summaries: ProjectListItem[] = [];

        for (let i = 0; i < projectIds.length; i += concurrencyLimit) {
          const batch = projectIds.slice(i, i + concurrencyLimit);
          const batchPromises = batch.map(async (projectId) => {
            try {
              const summary = await api.fetchProjectSummary(projectId);
              // Check if proposal PDF exists (HEAD request)
              try {
                const response = await fetch(
                  `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1"}/projects/${projectId}/proposal.pdf`,
                  { method: "HEAD" }
                );
                return { ...summary, proposal_pdf_available: response.ok };
              } catch {
                return { ...summary, proposal_pdf_available: false };
              }
            } catch (e) {
              // Project might not exist anymore
              return {
                project_id: projectId,
                status: "failed" as const,
                proposal_pdf_available: false,
              } as ProjectListItem;
            }
          });

          const batchResults = await Promise.all(batchPromises);
          summaries.push(...batchResults);
        }

        setProjects(summaries);
        setError(null);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load projects.");
        }
        console.error("Load error:", err);
      } finally {
        setLoading(false);
      }
    };

    loadProjects();
  }, []);

  // Filter and sort projects
  const filteredAndSortedProjects = useMemo(() => {
    let filtered = [...projects];

    // Apply filter
    if (filter === "bid_ready") {
      filtered = filtered.filter((p) => p.bid_ready === true);
    } else if (filter === "needs_review") {
      filtered = filtered.filter((p) => p.bid_ready === false);
    }

    // Apply sort
    filtered.sort((a, b) => {
      let aVal: number | string | undefined;
      let bVal: number | string | undefined;

      if (sortField === "cost") {
        aVal = a.total_cost ?? 0;
        bVal = b.total_cost ?? 0;
      } else if (sortField === "readiness_score") {
        aVal = a.readiness_score ?? 0;
        bVal = b.readiness_score ?? 0;
      } else if (sortField === "geometry_quality") {
        aVal = a.geometry_quality ?? "";
        bVal = b.geometry_quality ?? "";
      }

      if (aVal === undefined || bVal === undefined) return 0;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      } else {
        const aStr = String(aVal);
        const bStr = String(bVal);
        return sortDirection === "asc"
          ? aStr.localeCompare(bStr)
          : bStr.localeCompare(aStr);
      }
    });

    return filtered;
  }, [projects, filter, sortField, sortDirection]);

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedProjects(new Set(filteredAndSortedProjects.map((p) => p.project_id)));
    } else {
      setSelectedProjects(new Set());
    }
  };

  const handleSelectProject = (projectId: string, checked: boolean) => {
    const newSelected = new Set(selectedProjects);
    if (checked) {
      newSelected.add(projectId);
    } else {
      newSelected.delete(projectId);
    }
    setSelectedProjects(newSelected);
  };

  const handleExport = async () => {
    if (selectedProjects.size === 0) {
      alert("Please select at least one project to export.");
      return;
    }

    setExporting(true);
    try {
      const projectIds = Array.from(selectedProjects);
      const blob = await api.bulkExportProposals(projectIds, failIfMissingPdf);

      // Trigger download
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `proposals_export_${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError) {
        alert(`Export failed: ${err.message}`);
      } else {
        alert("Failed to export proposals. Please try again.");
      }
      console.error("Export error:", err);
    } finally {
      setExporting(false);
    }
  };

  const handleRemoveProject = (projectId: string) => {
    const stored = localStorage.getItem("recentProjects");
    if (stored) {
      const projectIds: string[] = JSON.parse(stored);
      const updated = projectIds.filter((id) => id !== projectId);
      localStorage.setItem("recentProjects", JSON.stringify(updated));
      setProjects(projects.filter((p) => p.project_id !== projectId));
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-2">Projects</h1>
          <p className="text-sm text-gray-600">
            Manage and export proposal PDFs for multiple projects
          </p>
        </div>
        <Link href="/">
          <Button variant="outline">
            <Upload className="h-4 w-4 mr-2" />
            Upload New PDF
          </Button>
        </Link>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {projects.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600 mb-4">No projects found.</p>
            <Link href="/">
              <Button>Upload Your First PDF</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Controls */}
          <Card className="mb-6">
            <CardContent className="pt-6">
              <div className="flex flex-wrap gap-4 items-center">
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-gray-500" />
                  <span className="text-sm font-medium">Filter:</span>
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value as FilterType)}
                    className="border rounded px-2 py-1 text-sm"
                  >
                    <option value="all">All Projects</option>
                    <option value="bid_ready">Bid Ready</option>
                    <option value="needs_review">Needs Review</option>
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <ArrowUpDown className="h-4 w-4 text-gray-500" />
                  <span className="text-sm font-medium">Sort:</span>
                  <select
                    value={sortField}
                    onChange={(e) => setSortField(e.target.value as SortField)}
                    className="border rounded px-2 py-1 text-sm"
                  >
                    <option value="cost">Total Cost</option>
                    <option value="readiness_score">Readiness Score</option>
                    <option value="geometry_quality">Geometry Quality</option>
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
                    }
                  >
                    {sortDirection === "asc" ? "↑" : "↓"}
                  </Button>
                </div>

                {selectedProjects.size > 0 && (
                  <div className="ml-auto flex items-center gap-2">
                    <span className="text-sm text-gray-600">
                      {selectedProjects.size} selected
                    </span>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={failIfMissingPdf}
                        onChange={(e) => setFailIfMissingPdf(e.target.checked)}
                      />
                      Fail if missing PDF
                    </label>
                    <Button
                      onClick={handleExport}
                      disabled={exporting}
                      variant="default"
                    >
                      {exporting ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Exporting...
                        </>
                      ) : (
                        <>
                          <Download className="h-4 w-4 mr-2" />
                          Export Selected ({selectedProjects.size})
                        </>
                      )}
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Table */}
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">
                      <input
                        type="checkbox"
                        checked={
                          filteredAndSortedProjects.length > 0 &&
                          filteredAndSortedProjects.every((p) =>
                            selectedProjects.has(p.project_id)
                          )
                        }
                        onChange={(e) => handleSelectAll(e.target.checked)}
                      />
                    </TableHead>
                    <TableHead>Project ID</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Bid Ready</TableHead>
                    <TableHead>Validation</TableHead>
                    <TableHead>Total Cost</TableHead>
                    <TableHead>Geometry Quality</TableHead>
                    <TableHead>PDF</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAndSortedProjects.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                        No projects match the current filter.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredAndSortedProjects.map((project) => (
                      <TableRow key={project.project_id}>
                        <TableCell>
                          <input
                            type="checkbox"
                            checked={selectedProjects.has(project.project_id)}
                            onChange={(e) =>
                              handleSelectProject(
                                project.project_id,
                                e.target.checked
                              )
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Link
                            href={`/projects/${project.project_id}`}
                            className="text-primary hover:underline font-mono text-sm"
                          >
                            {project.project_id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              project.status === "succeeded"
                                ? "default"
                                : project.status === "failed"
                                ? "destructive"
                                : "secondary"
                            }
                          >
                            {project.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {project.bid_ready !== undefined ? (
                            <Badge
                              variant={project.bid_ready ? "default" : "secondary"}
                            >
                              {project.readiness_stamp_text || (project.bid_ready ? "BID READY" : "PRELIMINARY")}
                            </Badge>
                          ) : (
                            <span className="text-sm text-gray-500">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {project.validation_score !== undefined ? (
                            <div className="flex items-center gap-1">
                              {project.validation_passed ? (
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                              ) : (
                                <XCircle className="h-4 w-4 text-red-500" />
                              )}
                              <span className="text-sm">
                                {(project.validation_score * 100).toFixed(0)}%
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-gray-500">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {project.total_cost !== undefined ? (
                            <span className="text-sm font-medium">
                              ${project.total_cost.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </span>
                          ) : (
                            <span className="text-sm text-gray-500">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {project.geometry_quality ? (
                            <Badge variant="outline">{project.geometry_quality}</Badge>
                          ) : (
                            <span className="text-sm text-gray-500">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {project.proposal_pdf_available ? (
                            <Badge variant="outline">Available</Badge>
                          ) : (
                            <Badge variant="outline" className="text-gray-500">
                              Missing
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Link href={`/projects/${project.project_id}`}>
                              <Button variant="ghost" size="sm">
                                Open
                              </Button>
                            </Link>
                            {project.proposal_pdf_available && (
                              <a
                                href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1"}/projects/${project.project_id}/proposal.pdf`}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <Button variant="ghost" size="sm">
                                  <Download className="h-3 w-3" />
                                </Button>
                              </a>
                            )}
                            {project.status === "failed" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRemoveProject(project.project_id)}
                              >
                                Remove
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

