"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { AlertCircle, Loader2, Box, Layers, Search, X } from "lucide-react";
import { ModelViewer3D } from "./ModelViewer3D";
import type { BidLineItem } from "@/lib/bid-linking";
import { buildSearchIndex, searchIndex, type SearchEntry, type SearchResult } from "@/lib/search-index";
import { Skeleton } from "@/components/ui/skeleton";

interface Model3DTabProps {
  projectId: string;
}

interface BoundingBox {
  min: { x: number; y: number; z: number };
  max: { x: number; y: number; z: number };
}

interface Building {
  building_id?: string | null;
  building_type: string;
  bounding_box: BoundingBox;
  is_subject?: boolean;
  evidence?: string;
}

interface Zone {
  zone_name: string;
  bounding_box: BoundingBox | null;
  zone_type?: "work_zone" | "room" | "building_mass" | null;
  page_number?: number;
  evidence?: string;
}

interface Model3D {
  buildings?: Building[];
  work_zones?: Zone[];
  missing_evidence?: string[];
  cross_section_regions?: Array<{
    region_id: string;
    region_type: "wall_assembly" | "parapet" | "roof_edge" | "floor_to_floor" | "foundation";
    bounding_box: BoundingBox;
    applies_to: string[];
    detail_refs: string[];
    evidence: string;
  }>;
  geometry?: {
    ghost_neighbors?: Array<{
      building_id: string;
      bounding_box: BoundingBox;
      opacity: number;
      label: string;
    }>;
    ground_plane?: {
      size: number;
      center: { x: number; y: number; z: number };
    };
    axis_labels?: Array<{
      direction: string;
      vector: { x: number; y: number; z: number };
      label: string;
    }>;
    dimension_hud?: {
      width_ft: number | null;
      depth_ft: number | null;
      height_ft: number | null;
      confidence: number;
      provenance: string;
    };
  };
}

interface InstitutionalGeometry {
  geometry_quality?: string;
  existing_building?: {
    area_gsf?: number;
  };
  addition_building?: {
    area_gsf?: number;
  };
  room_zones?: Array<{
    room_name: string;
    area_sf: number;
  }>;
}

interface BidProposal {
  line_items?: BidLineItem[];
}

interface EvidenceIndex {
  zone_evidence?: Array<{
    zone_id: string;
    zone_type: string;
    label?: string;
    evidence_references: Array<{
      page_number: number;
      sheet_id?: string;
      evidence_snippet: string;
      location_type?: string;
    }>;
    linked_bid_items: number[];
  }>;
}

interface ZoneCostMap {
  project_id: string;
  generated_at: string;
  zones: Array<{
    zone_id: string;
    zone_name: string;
    zone_type?: string | null;
    total_cost: number;
    division_breakdown: Record<string, number>;
    top_line_items: Array<{
      line_item_index: number;
      title: string;
      division: string;
      total_cost: number;
      contribution_percent: number;
      evidence_refs: Array<{
        page_number: number;
        sheet_id?: string | null;
        snippet?: string | null;
      }>;
    }>;
    linked_line_item_ids: number[];
    attribution_method: "evidence_index" | "keyword_fallback" | "none";
  }>;
  max_cost: number;
  min_cost: number;
}

interface DetailOverlayIndex {
  project_id: string;
  generated_at: string;
  regions: Array<{
    region_id: string;
    region_type: "wall_assembly" | "parapet" | "roof_edge" | "floor_to_floor" | "foundation";
    detail_ids: string[];
    detail_refs: Array<{
      detail_id: string;
      sheet_id: string;
      detail_label: string;
      page_number: number;
      detail_type: string;
    }>;
    evidence_pages: number[];
    snippets: Array<{
      page_number: number;
      sheet_id?: string | null;
      snippet: string;
      location_type?: string | null;
    }>;
  }>;
}

interface WorkPackage {
  id: string;
  title: string;
  division: string;
  trade?: string | null;
  estimated_cost: number;
  priority: "high" | "medium" | "low";
  confidence: number;
  basis_refs: string[];
  member_zone_ids: string[];
  member_line_item_ids: string[];
}

interface WorkPackageMap {
  project_id: string;
  packages: WorkPackage[];
  zone_to_package: Record<string, string>;
  line_item_to_package: Record<string, string>;
  generated_at: string;
  version: string;
}

export function Model3DTab({ projectId }: Model3DTabProps) {
  const [model3d, setModel3d] = useState<Model3D | null>(null);
  const [instGeometry, setInstGeometry] = useState<InstitutionalGeometry | null>(null);
  const [bidProposal, setBidProposal] = useState<BidProposal | null>(null);
  const [evidenceIndex, setEvidenceIndex] = useState<EvidenceIndex | null>(null);
  const [zoneCostMap, setZoneCostMap] = useState<ZoneCostMap | null>(null);
  const [detailOverlayIndex, setDetailOverlayIndex] = useState<DetailOverlayIndex | null>(null);
  const [workPackageMap, setWorkPackageMap] = useState<WorkPackageMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchSelectHandler, setSearchSelectHandler] = useState<((entry: SearchEntry) => void) | null>(null);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        // Load model_3d (returns null if 404)
        const modelData = await api.getArtifact<Model3D>(projectId, "model_3d");
        setModel3d(modelData); // Will be null if not available

        // Load extraction_result for institutional geometry (returns null if 404)
        const extractionData = await api.getArtifact<{ institutional_geometry_for_3d?: InstitutionalGeometry }>(
          projectId,
          "extraction_result"
        );
        if (extractionData?.institutional_geometry_for_3d) {
          setInstGeometry(extractionData.institutional_geometry_for_3d);
        }

        // First, get list of available artifacts
        const artifactsList = await api.listArtifacts(projectId);
        const availableArtifacts = new Set(artifactsList.artifacts.map(a => a.name));

        // Load bid_proposal only if available
        if (availableArtifacts.has("bid_proposal")) {
          const bidData = await api.getArtifact<BidProposal>(projectId, "bid_proposal");
          setBidProposal(bidData);
        } else {
          setBidProposal(null);
        }

        // Load evidence_index only if available
        if (availableArtifacts.has("evidence_index")) {
          const evidenceData = await api.getArtifact<EvidenceIndex>(projectId, "evidence_index");
          setEvidenceIndex(evidenceData);
        } else {
          setEvidenceIndex(null);
        }

        // Load zone_cost_map only if available
        if (availableArtifacts.has("zone_cost_map")) {
          const zoneCostData = await api.getArtifact<ZoneCostMap>(projectId, "zone_cost_map");
          setZoneCostMap(zoneCostData);
        } else {
          setZoneCostMap(null);
        }

        // Load detail_overlay_index only if available
        if (availableArtifacts.has("detail_overlay_index")) {
          const overlayData = await api.getArtifact<DetailOverlayIndex>(projectId, "detail_overlay_index");
          setDetailOverlayIndex(overlayData);
        } else {
          setDetailOverlayIndex(null);
        }

        // Load work_package_map only if available (Task 2)
        if (availableArtifacts.has("work_package_map")) {
          const packageMapData = await api.getArtifact<WorkPackageMap>(projectId, "work_package_map");
          setWorkPackageMap(packageMapData);
        } else {
          setWorkPackageMap(null);
        }

        setError(null);
      } catch (err) {
        // Only set error for non-404 errors (unexpected failures)
        if (err instanceof ApiError && err.status !== 404) {
          setError(err.message);
        } else if (!(err instanceof ApiError)) {
          setError("Failed to load 3D model data.");
        }
        // 404s are handled gracefully (null values)
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId]);

  // Build search index from loaded data
  const searchIndexData = useMemo(() => {
    if (!model3d && !bidProposal) return [];
    return buildSearchIndex({
      model3d: model3d || null,
      bid: bidProposal || null,
      evidenceIndex: evidenceIndex || null,
      detailOverlayIndex: detailOverlayIndex || null,
    });
  }, [model3d, bidProposal, evidenceIndex, detailOverlayIndex]);

  // Search handler
  useEffect(() => {
    if (searchQuery.trim().length === 0) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    const results = searchIndex(searchIndexData, searchQuery, 10);
    setSearchResults(results);
    setShowSearchResults(results.length > 0);
  }, [searchQuery, searchIndexData]);

  // Keyboard handlers
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showSearchResults) {
        setShowSearchResults(false);
        setSearchQuery("");
        searchInputRef.current?.blur();
      } else if (e.key === "Enter" && searchResults.length > 0 && document.activeElement === searchInputRef.current) {
        // Select first result
        const firstResult = searchResults[0];
        if (firstResult) {
          handleSearchSelect(firstResult.entry);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [searchResults, showSearchResults, searchInputRef]);

  const handleSearchSelect = (entry: SearchEntry) => {
    setSearchQuery("");
    setShowSearchResults(false);
    // Pass to ModelViewer3D via handler
    if (searchSelectHandler) {
      searchSelectHandler(entry);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 flex-1 max-w-md" />
          <Skeleton className="h-10 w-24" />
        </div>
        <div className="h-[600px] border rounded-lg">
          <Skeleton className="h-full w-full" />
        </div>
      </div>
    );
  }

  // Show error only if there's a real error (not just missing data)
  if (error && !model3d && !instGeometry && !loading) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  // Show empty state if no data available (but no error)
  if (!loading && !model3d && !instGeometry && !error) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          3D model data is not available yet. The pipeline may still be processing.
        </AlertDescription>
      </Alert>
    );
  }

  const buildingCount = model3d?.buildings?.length || 0;
  const zoneCount = model3d?.work_zones?.length || 0;
  const roomZoneCount = instGeometry?.room_zones?.length || 0;
  // Phase 9: Read geometry_quality from model3d (row-house) or instGeometry (institutional)
  const geometryQuality = (model3d as any)?.geometry_quality || instGeometry?.geometry_quality || (model3d ? "partial" : "missing");

  const hasViewableGeometry =
    model3d?.buildings && model3d.buildings.length > 0 && model3d.buildings.some((b) => b.bounding_box);

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div className="relative">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            ref={searchInputRef}
            type="text"
            placeholder="Search zones, regions, bid items, details..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              if (searchResults.length > 0) {
                setShowSearchResults(true);
              }
            }}
            className="pl-10 pr-10"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery("");
                setShowSearchResults(false);
              }}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Search Results Dropdown */}
        {showSearchResults && searchResults.length > 0 && (
          <div className="absolute z-50 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-96 overflow-y-auto">
            {searchResults.map((result, idx) => (
              <button
                key={result.entry.id}
                onClick={() => handleSearchSelect(result.entry)}
                className="w-full text-left px-4 py-2 hover:bg-gray-100 border-b last:border-b-0 flex items-center justify-between"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{result.entry.title}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="outline" className="text-xs">
                      {result.entry.type.replace(/_/g, " ")}
                    </Badge>
                    {result.entry.meta.pages && result.entry.meta.pages.length > 0 && (
                      <Badge variant="secondary" className="text-xs">
                        {result.entry.meta.pages.length} page{result.entry.meta.pages.length > 1 ? "s" : ""}
                      </Badge>
                    )}
                    {result.entry.meta.division && (
                      <Badge variant="secondary" className="text-xs">
                        {result.entry.meta.division}
                      </Badge>
                    )}
                  </div>
                </div>
                {idx === 0 && (
                  <span className="text-xs text-gray-400 ml-2">Enter</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Box className="h-4 w-4" />
              Buildings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{buildingCount}</div>
            {instGeometry?.existing_building && (
              <p className="text-sm text-gray-500 mt-1">
                Existing: {instGeometry.existing_building.area_gsf?.toLocaleString()} GSF
              </p>
            )}
            {instGeometry?.addition_building && (
              <p className="text-sm text-gray-500 mt-1">
                Addition: {instGeometry.addition_building.area_gsf?.toLocaleString()} GSF
              </p>
            )}
          </CardContent>
        </Card>

        <Card className={zoneCount < 10 ? "border-amber-500 bg-amber-50/50" : ""}>
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Zones
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${zoneCount < 10 ? "text-amber-700" : zoneCount >= 15 ? "text-emerald-700" : ""}`}>
              {zoneCount + roomZoneCount}
            </div>
            {zoneCount < 10 && (
              <p className="text-sm text-amber-700 font-medium mt-1">
                ⚠️ Low zone count — 3D may be limited
              </p>
            )}
            {zoneCount >= 10 && zoneCount < 15 && (
              <p className="text-sm text-gray-600 mt-1">
                Work zones: {zoneCount}
              </p>
            )}
            {zoneCount >= 15 && (
              <p className="text-sm text-emerald-700 font-medium mt-1">
                ✅ Good zone coverage
              </p>
            )}
            {roomZoneCount > 0 && (
              <p className="text-sm text-gray-500 mt-1">
                Room zones: {roomZoneCount}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Geometry Quality</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge
              variant={
                geometryQuality === "authoritative"
                  ? "default"
                  : geometryQuality === "ok"
                  ? "secondary"
                  : geometryQuality === "derived_from_area"
                  ? "secondary"
                  : "outline"
              }
            >
              {geometryQuality}
            </Badge>
            {/* Phase 9: Helper message for partial geometry */}
            {geometryQuality === "partial" && (
              <p className="text-xs text-muted-foreground mt-2 italic">
                This is an evidence map, not a BIM model yet.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Phase 9: Helper message banner for partial geometry */}
      {geometryQuality === "partial" && (
        <Alert className="border-amber-200 bg-amber-50">
          <AlertCircle className="h-4 w-4 text-amber-600" />
          <AlertDescription className="text-sm text-amber-900">
            <strong>Note:</strong> This is an evidence map, not a BIM model yet. Zones are generated deterministically from building dimensions to help visualize work areas and link to evidence.
          </AlertDescription>
        </Alert>
      )}

      {/* 3D Viewer */}
      {hasViewableGeometry && model3d ? (
        <ModelViewer3D
          buildings={model3d.buildings || []}
          zones={model3d.work_zones || []}
          bidItems={bidProposal?.line_items}
          projectId={projectId}
          zoneCostMap={zoneCostMap}
          detailOverlayIndex={detailOverlayIndex}
          workPackageMap={workPackageMap}
          crossSectionRegions={model3d.cross_section_regions}
          ghostNeighbors={(model3d as any)?.geometry?.ghost_neighbors}
          groundPlane={(model3d as any)?.geometry?.ground_plane}
          axisLabels={(model3d as any)?.geometry?.axis_labels}
          dimensionHud={(model3d as any)?.geometry?.dimension_hud}
          onSearchSelectRef={(handler) => setSearchSelectHandler(() => handler)}
        />
      ) : (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {model3d
              ? "3D model data is available but no viewable geometry found (missing bounding boxes)."
              : "No 3D model data available. Upload and process a PDF to generate 3D geometry."}
          </AlertDescription>
        </Alert>
      )}

      {roomZoneCount > 0 && instGeometry?.room_zones && (
        <Card>
          <CardHeader>
            <CardTitle>Room Zones</CardTitle>
            <CardDescription>Top 10 largest rooms</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {instGeometry.room_zones
                .sort((a, b) => (b.area_sf || 0) - (a.area_sf || 0))
                .slice(0, 10)
                .map((room, idx) => (
                  <div key={idx} className="flex justify-between items-center p-2 border rounded">
                    <span className="font-medium">{room.room_name}</span>
                    <span className="text-sm text-gray-600">
                      {room.area_sf.toLocaleString()} SF
                    </span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {model3d?.missing_evidence && model3d.missing_evidence.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Missing Evidence</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {model3d.missing_evidence.map((item, idx) => (
                <Badge key={idx} variant="outline" className="mr-2">
                  {item}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

