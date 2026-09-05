/** API client for Construction Bid AI backend (Phase 6.1). */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

export interface ArtifactInfo {
  name: string;
  url: string;
}

export interface BidReadiness {
  bid_ready: boolean;
  readiness_score: number;
  reasons_blocking: string[];
  warnings: string[];
  derived_from: Record<string, any>;
  readiness_stamp_text: string;
}

export interface ProjectSummary {
  project_id: string;
  status: "running" | "succeeded" | "failed" | "completed" | "uploaded" | "queued" | "not_started";
  last_updated?: string;
  validation_score?: number;
  validation_passed?: boolean;
  total_cost?: number;
  bid_ready?: boolean;
  estimate_mode?: "conceptual" | "bid_ready";
  geometry_quality?: string;
  readiness_score?: number;
  readiness_stamp_text?: string;
  readiness_reasons_blocking?: string[];
  readiness_warnings?: string[];
}

// Re-export for convenience
export type { ProjectSummary as ProjectListItem } from "./types";

export interface ProjectStatus {
  project_id: string;
  status: string;
  current_stage?: string;
  stages: Array<{
    stage_name: string;
    status: string;
    attempts: number;
    started_at?: string;
    finished_at?: string;
    duration_seconds?: number;
    elapsed_seconds?: number;
    artifacts?: Record<string, string>;
    error?: string;
  }>;
  last_updated: string | null;
  page_count?: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public response?: any
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  // Check if this is an expected 404 endpoint (optional resources)
  const isExpected404 = endpoint.includes("/artifacts/") || 
                        endpoint.includes("/pages") ||
                        endpoint.includes("/proposal.pdf") ||
                        endpoint.includes("/contractor_proposal.pdf") ||
                        endpoint.includes("/bid_readiness_v2") ||
                        endpoint.includes("/contractor_bid");
  
  const requestInit: RequestInit = {
    ...options,
    cache: options?.cache ?? "no-store",
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
      ...options?.headers,
    },
  };

  let response: Response;
  try {
    response = await fetch(url, requestInit);
  } catch (networkError) {
    // Network errors (connection failures) should still be logged
    if (!isExpected404) {
      console.error("Network error:", networkError);
    }
    throw networkError;
  }

  if (!response.ok) {
    // For expected 404s, return null silently (no console errors)
    if (response.status === 404 && isExpected404) {
      return null as T;
    }
    
    const errorData = await response.json().catch(() => ({}));
    // Only log unexpected errors (not 404s on expected endpoints)
    if (!(response.status === 404 && isExpected404)) {
      console.error(`API Error ${response.status}:`, errorData);
    }
    throw new ApiError(
      errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

export const api = {
  /** List available artifacts for a project. */
  async listArtifacts(projectId: string): Promise<{ artifacts: ArtifactInfo[] }> {
    return fetchApi(`/projects/${projectId}/artifacts`);
  },

  /** Get a specific artifact JSON. */
  /** Get artifact (returns null if not found - no console errors for 404s). */
  async getArtifact<T = any>(projectId: string, artifactName: string): Promise<T | null> {
    try {
      // Use fetchApi which already handles expected 404s silently
      const result = await fetchApi<T>(`/projects/${projectId}/artifacts/${artifactName}`);
      return result;
    } catch (err) {
      // Artifacts are optional - 404s are expected and handled silently
      // fetchApi already returns null for expected 404s, but catch any unexpected errors
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      // Only log non-404 errors
      if (!(err instanceof ApiError && err.status === 404)) {
        console.error("Unexpected error fetching artifact:", err);
      }
      return null; // Return null for any error to prevent UI crashes
    }
  },

  /** Get project summary. */
  async getProjectSummary(projectId: string): Promise<ProjectSummary> {
    return fetchApi(`/projects/${projectId}/summary`);
  },

  /** Get detailed pipeline status with stages. */
  async getProjectStatus(projectId: string): Promise<ProjectStatus> {
    return fetchApi(`/projects/${projectId}/status`);
  },

  /** Get page index job status. */
  async getPageIndexJobStatus(projectId: string): Promise<{
    status: "not_started" | "running" | "succeeded" | "failed" | "unknown" | "queued";
    project_id: string;
    progress?: {
      total_pages: number;
      completed_pages: number;
      cached_pages: number;
      failed_pages: number;
      updated_at: string;
    } | null;
    message?: string;
    error?: string;
  }> {
    return fetchApi(`/projects/${projectId}/jobs/page-index/status`);
  },

  /** Upload a PDF file (saves only, does not process). */
  async uploadPdf(file: File): Promise<{ project_id: string; page_count: number; status: string }> {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${API_BASE_URL}/projects/upload`;
    
    try {
      const response = await fetch(url, {
        method: "POST",
        body: formData,
        // Don't set Content-Type header - browser will set it with boundary for multipart/form-data
      });

      if (!response.ok) {
        let errorData: any = {};
        try {
          errorData = await response.json();
        } catch {
          // If response is not JSON, use status text
          errorData = { detail: response.statusText };
        }
        throw new ApiError(
          errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
          response.status,
          errorData
        );
      }

      return response.json();
    } catch (err) {
      // Handle network errors (CORS, connection refused, etc.)
      if (err instanceof TypeError && err.message.includes("fetch")) {
        throw new ApiError(
          `Cannot connect to backend at ${url}. Is the backend running?`,
          0,
          { network_error: true, original_error: err.message }
        );
      }
      throw err;
    }
  },

  /** Run pipeline for a project (enqueues background job). */
  async runProject(projectId: string): Promise<{ project_id: string; job_id?: string; status: string }> {
    return fetchApi(`/projects/${projectId}/run`, {
      method: "POST",
    });
  },

  /** Get manual overrides for a project. */
  async getManualOverrides(projectId: string): Promise<{
    roof_area_sf?: number;
    membrane_type?: string;
    insulation_thickness_in?: number;
    updated_at?: string;
  }> {
    return fetchApi(`/projects/${projectId}/manual_overrides`);
  },

  /** Update manual overrides for a project. */
  async updateManualOverrides(
    projectId: string,
    payload: {
      roof_area_sf?: number | null;
      membrane_type?: string | null;
      insulation_thickness_in?: number | null;
    }
  ): Promise<{ success: boolean; overrides: any }> {
    return fetchApi(`/projects/${projectId}/manual_overrides`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** Generate proposal PDF (enqueue job). */
  async generateProposalPdf(projectId: string): Promise<{ job_id: string; project_id: string; status: string }> {
    return fetchApi(`/projects/${projectId}/proposal.pdf`, {
      method: "POST",
    });
  },

  /** Get PDF generation job status. */
  async getJobStatus(jobId: string): Promise<{ job_id: string; status: string; project_id?: string; error?: string }> {
    return fetchApi(`/jobs/${jobId}`);
  },

  /** Get bid readiness assessment (Phase 6.5). */
  async getBidReadiness(projectId: string): Promise<BidReadiness> {
    return fetchApi(`/projects/${projectId}/bid_readiness`);
  },

  /** Get bid readiness v2 assessment (Phase 10.1). Returns null if not available. */
  async getBidReadinessV2(projectId: string): Promise<{
    conceptual_ready: boolean;
    contractor_ready: boolean;
    blocking_reasons_contractor: string[];
    warnings_contractor: string[];
    derived_from: Record<string, any>;
  } | null> {
    try {
      return await fetchApi(`/projects/${projectId}/bid_readiness_v2`);
    } catch (err) {
      // If 404, return null (readiness v2 not available - that's OK)
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /** Fetch project summary (Phase 6.6). */
  async fetchProjectSummary(projectId: string): Promise<ProjectSummary> {
    return fetchApi(`/projects/${projectId}/summary`);
  },

  /** Bulk export proposals as ZIP (Phase 6.6). */
  async bulkExportProposals(
    projectIds: string[],
    failIfMissingPdf: boolean = false
  ): Promise<Blob> {
    const url = `${API_BASE_URL}/projects/export/proposals.zip`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_ids: projectIds,
        include_manifest: true,
        fail_if_missing_pdf: failIfMissingPdf,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }

    return response.blob();
  },

  /** List pages for a project (Phase 8.6A). Returns null if pages not available. */
  async listPages(projectId: string): Promise<{
    project_id: string;
    page_count: number;
    pages: Array<{ page_number: number; url: string }>;
  } | null> {
    try {
      return await fetchApi(`/projects/${projectId}/pages`);
    } catch (err) {
      // If 404, return null (pages not generated yet - that's OK)
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /** Get page image URL (Phase 8.6A). */
  getPageImageUrl(projectId: string, pageNumber: number): string {
    return `${API_BASE_URL}/projects/${projectId}/pages/${pageNumber}.png`;
  },

  /** Get source PDF URL (Phase 8.6C). */
  getSourcePdfUrl(projectId: string): string {
    return `${API_BASE_URL}/projects/${projectId}/source.pdf`;
  },

  /** Get contractor bid (Phase 9.4B). Returns null if not generated. */
  async getContractorBid(projectId: string): Promise<any | null> {
    try {
      return await fetchApi(`/projects/${projectId}/contractor_bid`);
    } catch (err) {
      // If 404, return null (contractor bid not generated yet - that's OK)
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /** Generate contractor bid (Phase 9.4B). */
  async generateContractorBid(projectId: string): Promise<any> {
    return fetchApi(`/projects/${projectId}/contractor_bid`, {
      method: "POST",
    });
  },

  /** Generate contractor proposal PDF (Phase 9.6). */
  async generateContractorProposalPdf(projectId: string): Promise<{ job_id: string; project_id: string; status: string }> {
    return fetchApi(`/projects/${projectId}/contractor_proposal.pdf`, {
      method: "POST",
    });
  },
};

