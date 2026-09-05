"use client";

import { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { openEvidenceDrawer } from "@/lib/evidence-drawer-helper";
import type { EvidenceRef } from "@/lib/evidence-normalizer";
import { AlertCircle, Loader2, Search } from "lucide-react";

interface EvidenceTabProps {
  projectId: string;
}

interface ExtractionResult {
  scope_of_work?: Array<{
    item: string;
    description: string;
    page_number?: number;
    evidence_snippet?: string;
  }>;
  material_specifications?: Array<{
    material_name: string;
    page_number?: number;
    evidence_snippet?: string;
  }>;
  quantity_takeoff?: Array<{
    item: string;
    quantity?: number;
    unit?: string;
    page_number?: number;
    evidence_snippet?: string;
  }>;
  room_program?: {
    rooms?: Array<{
      room_name: string;
      room_number?: string;
      area_sf?: number;
      page_number?: number;
      evidence_snippet?: string;
    }>;
  };
}

interface EvidenceItem {
  type: string;
  name: string;
  details: string;
  page?: number;
  snippet?: string;
  evidenceRefs: EvidenceRef[];
}

interface DrawerState {
  open: boolean;
  title: string;
  subtitle?: string;
  evidence: EvidenceRef[];
  initialPage?: number;
  initialEvidenceIndex?: number;
}

const buildEvidenceRef = (page?: number, snippet?: string | null, type?: string): EvidenceRef[] => {
  const trimmedSnippet = snippet?.trim() ?? null;
  const normalizedPage = typeof page === "number" && Number.isFinite(page) ? page : 0;

  if ((normalizedPage <= 0 || Number.isNaN(normalizedPage)) && !trimmedSnippet) {
    return [];
  }

  return [
    {
      page_number: normalizedPage,
      sheet_id: null,
      sheet_title: null,
      location_type: type ? type.toLowerCase() : null,
      snippet: trimmedSnippet,
      detail_refs: [],
      source: "extraction",
      bbox: null,
      bbox_source: "none",
    },
  ];
};

export function EvidenceTab({ projectId }: EvidenceTabProps) {
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [drawerState, setDrawerState] = useState<DrawerState>({
    open: false,
    title: "",
    subtitle: undefined,
    evidence: [],
    initialPage: undefined,
    initialEvidenceIndex: undefined,
  });

  useEffect(() => {
    const loadExtraction = async () => {
      try {
        const data = await api.getArtifact<ExtractionResult>(projectId, "extraction_result");
        setExtraction(data);
        setError(null);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setError("Extraction result not found. The project may still be processing.");
        } else if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load extraction result.");
        }
      } finally {
        setLoading(false);
      }
    };

    loadExtraction();
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!extraction) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>No extraction data available</AlertDescription>
      </Alert>
    );
  }

  // Collect all evidence items
  const evidenceItems: EvidenceItem[] = [];

  if (extraction.scope_of_work) {
    for (const item of extraction.scope_of_work) {
      evidenceItems.push({
        type: "Scope",
        name: item.item,
        details: item.description,
        page: item.page_number,
        snippet: item.evidence_snippet,
        evidenceRefs: buildEvidenceRef(item.page_number, item.evidence_snippet, "scope"),
      });
    }
  }

  if (extraction.material_specifications) {
    for (const item of extraction.material_specifications) {
      evidenceItems.push({
        type: "Material",
        name: item.material_name,
        details: "",
        page: item.page_number,
        snippet: item.evidence_snippet,
        evidenceRefs: buildEvidenceRef(item.page_number, item.evidence_snippet, "material"),
      });
    }
  }

  if (extraction.quantity_takeoff) {
    for (const item of extraction.quantity_takeoff) {
      evidenceItems.push({
        type: "Quantity",
        name: item.item,
        details: `${item.quantity || "N/A"} ${item.unit || ""}`,
        page: item.page_number,
        snippet: item.evidence_snippet,
        evidenceRefs: buildEvidenceRef(item.page_number, item.evidence_snippet, "quantity"),
      });
    }
  }

  if (extraction.room_program?.rooms) {
    for (const room of extraction.room_program.rooms) {
      evidenceItems.push({
        type: "Room",
        name: room.room_name,
        details: `${room.area_sf || "N/A"} SF`,
        page: room.page_number,
        snippet: room.evidence_snippet,
        evidenceRefs: buildEvidenceRef(room.page_number, room.evidence_snippet, "room"),
      });
    }
  }

  // Filter by search query
  const filteredItems = evidenceItems.filter((item) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      item.name.toLowerCase().includes(query) ||
      item.details.toLowerCase().includes(query) ||
      item.snippet?.toLowerCase().includes(query) ||
      false
    );
  });

  const handleOpenEvidence = (item: EvidenceItem) => {
    if (!item.evidenceRefs.length) {
      return;
    }

    openEvidenceDrawer({
      projectId,
      evidenceRefs: item.evidenceRefs,
      initialPage: item.page,
      source: "search",
      title: `${item.type}: ${item.name}`,
      subtitle: item.details || undefined,
      onOpen: ({ open, title, subtitle, evidence, initialPage, initialEvidenceIndex }) =>
        setDrawerState({
          open,
          title,
          subtitle,
          evidence,
          initialPage,
          initialEvidenceIndex,
        }),
    });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Evidence Items</CardTitle>
          <CardDescription>
            Searchable list of extracted items with page references
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search evidence items..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          <div className="space-y-2">
            {filteredItems.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No evidence items found</p>
            ) : (
              filteredItems.map((item, idx) => (
                <Card key={idx}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline">{item.type}</Badge>
                          <span className="font-medium">{item.name}</span>
                        </div>
                        {item.details && (
                          <p className="text-sm text-gray-600 mb-2">{item.details}</p>
                        )}
                        {item.snippet && (
                          <p className="text-sm text-gray-500 italic">"{item.snippet}"</p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        {item.page && (
                          <Badge variant="secondary">Page {item.page}</Badge>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleOpenEvidence(item)}
                          disabled={item.evidenceRefs.length === 0}
                        >
                          View Evidence
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </CardContent>
      </Card>
      <EvidenceDrawer
        open={drawerState.open}
        onOpenChange={(open) => setDrawerState((prev) => ({ ...prev, open }))}
        title={drawerState.title}
        subtitle={drawerState.subtitle}
        evidence={drawerState.evidence}
        projectId={projectId}
        initialPage={drawerState.initialPage}
        initialEvidenceIndex={drawerState.initialEvidenceIndex}
      />
    </div>
  );
}






