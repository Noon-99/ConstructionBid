/** Type definitions for project data (Phase 6.6). */

export interface ProjectSummary {
  project_id: string;
  status: "running" | "succeeded" | "failed" | "completed";
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

export interface ProjectListItem extends ProjectSummary {
  proposal_pdf_available?: boolean;
}






