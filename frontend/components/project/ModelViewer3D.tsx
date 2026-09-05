"use client";

import { useRef, useMemo, useState, Suspense, useEffect, Fragment } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, PerspectiveCamera, Html } from "@react-three/drei";
import * as THREE from "three";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X, RotateCcw, FileText, Maximize2, Minimize2 } from "lucide-react";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { useEvidenceIndex } from "@/lib/useEvidenceIndex";
import {
  getBoundingBoxDimensions,
  getFootprintArea,
  getVolume,
  getSceneBoundingBox,
  type BoundingBox,
} from "@/lib/geometry-utils";
import type React from "react";
import { findLinkedBidItems, type BidLineItem } from "@/lib/bid-linking";
import type { SearchEntry } from "@/lib/search-index";
import { computeFocusFromBBox, flyTo } from "@/lib/camera-utils";
import { getContractorLabel, formatPackageTitle } from "@/lib/contractor-labels";

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

// EvidenceIndex type is now handled by useEvidenceIndex hook

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

interface CrossSectionRegion {
  region_id: string;
  region_type: "wall_assembly" | "parapet" | "roof_edge" | "floor_to_floor" | "foundation";
  bounding_box: BoundingBox;
  applies_to: string[];
  detail_refs: string[];
  evidence: string;
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

interface GhostNeighbor {
  building_id: string;
  bounding_box: BoundingBox;
  opacity: number;
  label: string;
}

interface GroundPlane {
  size: number;
  center: { x: number; y: number; z: number };
}

interface AxisLabel {
  direction: string;
  vector: { x: number; y: number; z: number };
  label: string;
}

interface DimensionHUD {
  width_ft: number | null;
  depth_ft: number | null;
  height_ft: number | null;
  confidence: number;
  provenance: string;
}

interface ModelViewer3DProps {
  buildings: Building[];
  zones: Zone[];
  bidItems?: BidLineItem[];
  projectId: string;
  zoneCostMap?: ZoneCostMap | null;
  detailOverlayIndex?: DetailOverlayIndex | null;
  workPackageMap?: WorkPackageMap | null;
  crossSectionRegions?: CrossSectionRegion[];
  ghostNeighbors?: GhostNeighbor[];
  groundPlane?: GroundPlane | null;
  axisLabels?: AxisLabel[];
  dimensionHud?: DimensionHUD | null;
  onSelectionChange?: (selected: Building | Zone | null) => void;
  onSearchSelectRef?: (handler: (entry: any) => void) => void;
}

// Building box component
function BuildingBox({
  building,
  isSelected,
  onSelect,
}: {
  building: Building;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const dims = getBoundingBoxDimensions(building.bounding_box);
  const center = {
    x: (building.bounding_box.min.x + building.bounding_box.max.x) / 2,
    y: (building.bounding_box.min.y + building.bounding_box.max.y) / 2,
    z: (building.bounding_box.min.z + building.bounding_box.max.z) / 2,
  };

  // Neutral material for buildings
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: isSelected ? "#4a90e2" : "#888888",
        opacity: 0.7,
        transparent: true,
        emissive: isSelected ? "#1a4a8a" : "#000000",
        emissiveIntensity: isSelected ? 0.3 : 0,
      }),
    [isSelected]
  );

  return (
    <mesh
      ref={meshRef}
      position={[center.x, center.z, center.y]} // Y-up to Z-up conversion
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        document.body.style.cursor = "default";
      }}
    >
      <boxGeometry args={[dims.width, dims.height, dims.depth]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// Zone box component
function ZoneBox({
  zone,
  isSelected,
  onSelect,
  heatmapMode,
  zoneCostData,
  maxCost,
  minCost,
  viewMode,
  packageData,
  packageMaxCost,
  packageMinCost,
}: {
  zone: Zone;
  isSelected: boolean;
  onSelect: () => void;
  heatmapMode: "none" | "cost" | "division";
  zoneCostData?: {
    total_cost: number;
    division_breakdown: Record<string, number>;
    attribution_method: string;
  } | null;
  maxCost: number;
  minCost: number;
  viewMode: "zones" | "packages";
  packageData?: WorkPackage | null;
  packageMaxCost: number;
  packageMinCost: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);

  if (!zone.bounding_box) return null;

  const dims = getBoundingBoxDimensions(zone.bounding_box);
  const center = {
    x: (zone.bounding_box.min.x + zone.bounding_box.max.x) / 2,
    y: (zone.bounding_box.min.y + zone.bounding_box.max.y) / 2,
    z: (zone.bounding_box.min.z + zone.bounding_box.max.z) / 2,
  };

  // Task 6: Color calculation based on heatmap mode and view mode
  const getColor = () => {
    if (isSelected) return "#4a90e2";
    
    // Task 6: In Packages mode, color by normalized package cost (green→red)
    if (viewMode === "packages" && packageData) {
      const packageCost = packageData.estimated_cost;
      
      // Normalize cost to 0-1 range
      let normalized = 0.5;
      if (packageMaxCost > packageMinCost) {
        normalized = (packageCost - packageMinCost) / (packageMaxCost - packageMinCost);
      } else if (packageMaxCost > 0) {
        normalized = 0.5; // All packages have same cost
      } else {
        return "#9e9e9e"; // No cost data
      }
      
      // Interpolate from green (low) to red (high) based on normalized cost
      const r = Math.min(255, Math.floor(normalized * 255));
      const g = Math.min(255, Math.floor((1 - normalized) * 255));
      const b = 0;
      return `rgb(${r}, ${g}, ${b})`;
    }
    
    if (heatmapMode === "cost") {
      if (!zoneCostData) {
        return "#9e9e9e"; // Gray for no data
      }
      const cost = zoneCostData.total_cost || 0;
      if (cost === 0) {
        return "#9e9e9e"; // Gray for zero cost
      }
      // Normalize cost to 0-1 range
      // If maxCost === minCost (all zones have same cost or all are 0), use middle color
      let normalized = 0.5;
      if (maxCost > minCost) {
        normalized = (cost - minCost) / (maxCost - minCost);
      } else if (maxCost > 0) {
        // All zones have same non-zero cost, use middle color
        normalized = 0.5;
      } else {
        // All costs are 0, shouldn't reach here but gray anyway
        return "#9e9e9e";
      }
      // Interpolate from green (low) to red (high)
      const r = Math.min(255, Math.floor(normalized * 255));
      const g = Math.min(255, Math.floor((1 - normalized) * 255));
      const b = 0;
      return `rgb(${r}, ${g}, ${b})`;
    }
    
    if (heatmapMode === "division") {
      if (!zoneCostData || Object.keys(zoneCostData.division_breakdown).length === 0) {
        return "#9e9e9e"; // Gray for no data
      }
      // Get top division by cost
      const topDivision = Object.entries(zoneCostData.division_breakdown)
        .sort(([, a], [, b]) => b - a)[0]?.[0];
      // Deterministic color mapping per division
      const divisionColors: Record<string, string> = {
        "04 Masonry": "#ff9800", // Orange
        "05 Metals": "#2196f3", // Blue
        "06 Wood": "#4caf50", // Green
        "07 Thermal": "#9c27b0", // Purple
        "08 Openings": "#f44336", // Red
        "09 Finishes": "#00bcd4", // Cyan
        "10 Specialties": "#ffc107", // Amber
      };
      return divisionColors[topDivision] || "#9e9e9e";
    }
    
    // Default: Different colors for room vs work zones
    if (zone.zone_type === "room") return "#90caf9"; // Light blue for rooms
    if (zone.zone_type === "work_zone") return "#ff9800"; // Orange for work zones
    return "#9e9e9e"; // Gray default
  };

  const color = getColor();
  
  // Task 6: Determine opacity and pattern based on confidence
  const getOpacity = () => {
    if (viewMode === "packages" && packageData) {
      const confidence = packageData.confidence;
      if (confidence >= 0.7) {
        return 0.7; // High confidence: solid
      } else if (confidence >= 0.4) {
        return 0.5; // Medium confidence: slight transparency
      } else {
        return 0.3; // Low confidence: translucent
      }
    }
    return 0.6; // Default for zones view
  };
  
  const opacity = getOpacity();
  
  // Task 6: Create material with confidence-based opacity
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: color,
        opacity: opacity,
        transparent: true,
        emissive: isSelected ? "#1a4a8a" : "#000000",
        emissiveIntensity: isSelected ? 0.4 : 0,
        // Medium confidence: slight wireframe for "hatch" effect
        wireframe: viewMode === "packages" && packageData && packageData.confidence >= 0.4 && packageData.confidence < 0.7,
      }),
    [isSelected, color, opacity, viewMode, packageData]
  );
  
  // Force material update when color or opacity changes
  useEffect(() => {
    if (material) {
      material.color.set(color);
      material.opacity = opacity;
      material.wireframe = viewMode === "packages" && packageData && packageData.confidence >= 0.4 && packageData.confidence < 0.7;
      material.needsUpdate = true;
    }
  }, [material, color, opacity, viewMode, packageData]);

  return (
    <mesh
      ref={meshRef}
      position={[center.x, center.z, center.y]} // Y-up to Z-up conversion
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        document.body.style.cursor = "default";
      }}
    >
      <boxGeometry args={[dims.width, dims.height, dims.depth]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// Cross-section region box component
function CrossSectionRegionBox({
  region,
  isSelected,
  onSelect,
}: {
  region: CrossSectionRegion;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const dims = getBoundingBoxDimensions(region.bounding_box);
  const center = {
    x: (region.bounding_box.min.x + region.bounding_box.max.x) / 2,
    y: (region.bounding_box.min.y + region.bounding_box.max.y) / 2,
    z: (region.bounding_box.min.z + region.bounding_box.max.z) / 2,
  };

  // Color by region type
  const getColor = () => {
    if (isSelected) return "#4a90e2";
    const colors: Record<string, string> = {
      parapet: "#ff9800",
      roof_edge: "#f44336",
      wall_assembly: "#2196f3",
      floor_to_floor: "#4caf50",
      foundation: "#9c27b0",
    };
    return colors[region.region_type] || "#9e9e9e";
  };

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: getColor(),
        opacity: isSelected ? 0.5 : 0.3,
        transparent: true,
        emissive: isSelected ? "#1a4a8a" : "#000000",
        emissiveIntensity: isSelected ? 0.3 : 0,
        wireframe: false,
      }),
    [isSelected, region.region_type]
  );

  return (
    <mesh
      ref={meshRef}
      position={[center.x, center.z, center.y]} // Y-up to Z-up conversion
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        document.body.style.cursor = "default";
      }}
    >
      <boxGeometry args={[dims.width, dims.height, dims.depth]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// Auto-frame camera component (runs once on mount, not every frame)
function AutoFrameCamera({
  buildings,
  zones,
}: {
  buildings: Building[];
  zones: Zone[];
}) {
  const { camera } = useThree();
  const sceneBbox = useMemo(
    () => getSceneBoundingBox(buildings, zones),
    [buildings, zones]
  );

  // Only frame once on mount, not every frame (prevents overriding OrbitControls)
  useEffect(() => {
    if (!sceneBbox) return;

    const dims = getBoundingBoxDimensions(sceneBbox);
    const center = {
      x: (sceneBbox.min.x + sceneBbox.max.x) / 2,
      y: (sceneBbox.min.y + sceneBbox.max.y) / 2,
      z: (sceneBbox.min.z + sceneBbox.max.z) / 2,
    };

    // Calculate distance to frame the scene
    const maxDim = Math.max(dims.width, dims.depth, dims.height);
    const distance = maxDim * 2.5;

    // Position camera (only once)
    camera.position.set(center.x + distance, center.z + distance * 0.7, center.y + distance);
    camera.lookAt(center.x, center.z, center.y);
    camera.updateProjectionMatrix();
  }, [camera, sceneBbox]); // Only run when camera or sceneBbox changes

  return null;
}

// Label component for 3D objects
function ObjectLabel({
  position,
  text,
  isHighlighted,
}: {
  position: [number, number, number];
  text: string;
  isHighlighted?: boolean;
}) {
  // Always show labels
  if (!text) return null;
  
  return (
    <Html 
      position={position} 
      center 
      zIndexRange={[100, 0]} 
      style={{ pointerEvents: "none" }}
      occlude
    >
      <div
        className={`px-2 py-1 rounded text-xs font-medium bg-black/90 text-white whitespace-nowrap shadow-lg border border-white/20 ${
          isHighlighted ? "ring-2 ring-blue-400" : ""
        }`}
        style={{ 
          userSelect: "none",
          WebkitFontSmoothing: "antialiased",
          textShadow: "0 1px 2px rgba(0,0,0,0.8)"
        }}
      >
        {text}
      </div>
    </Html>
  );
}

// Main 3D scene component
function Scene3D({
  buildings,
  zones,
  selected,
  onSelect,
  controlsRef,
  heatmapMode,
  zoneCostMap,
  viewMode,
  crossSectionRegions,
  selectedRegion,
  onSelectRegion,
  labelMode,
  highlightedId,
  cameraRef,
  packageViewMode,
  workPackageMap,
  onSelectPackage,
  ghostNeighbors,
  groundPlane,
  axisLabels,
  dimensionHud,
}: {
  buildings: Building[];
  zones: Zone[];
  selected: Building | Zone | null;
  onSelect: (item: Building | Zone | null) => void;
  controlsRef: React.RefObject<any>;
  heatmapMode: "none" | "cost" | "division";
  zoneCostMap?: ZoneCostMap | null;
  viewMode: "normal" | "section";
  crossSectionRegions?: CrossSectionRegion[];
  selectedRegion: CrossSectionRegion | null;
  onSelectRegion: (region: CrossSectionRegion | null) => void;
  labelMode: "off" | "zones" | "all";
  highlightedId: string | null;
  cameraRef: React.RefObject<THREE.PerspectiveCamera | null>;
  packageViewMode: "zones" | "packages";
  workPackageMap?: WorkPackageMap | null;
  onSelectPackage?: (packageId: string | null) => void;
  ghostNeighbors?: GhostNeighbor[];
  groundPlane?: GroundPlane | null;
  axisLabels?: AxisLabel[];
  dimensionHud?: DimensionHUD | null;
}) {
  // Store camera reference
  useEffect(() => {
    if (controlsRef.current?.object) {
      cameraRef.current = controlsRef.current.object as THREE.PerspectiveCamera;
    }
  }, [controlsRef]);
  
  // Task 6: Calculate package cost range for normalization
  const packageCostRange = useMemo(() => {
    if (!workPackageMap || packageViewMode !== "packages") {
      return { min: 0, max: 0 };
    }
    const costs = workPackageMap.packages.map(p => p.estimated_cost);
    if (costs.length === 0) {
      return { min: 0, max: 0 };
    }
    return {
      min: Math.min(...costs),
      max: Math.max(...costs),
    };
  }, [workPackageMap, packageViewMode]);
  
  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <gridHelper args={[100, 100]} />
      <axesHelper args={[20]} />

      <AutoFrameCamera buildings={buildings} zones={zones} />

      {buildings.map((building, idx) => {
        const center = {
          x: (building.bounding_box.min.x + building.bounding_box.max.x) / 2,
          y: (building.bounding_box.min.y + building.bounding_box.max.y) / 2,
          z: (building.bounding_box.min.z + building.bounding_box.max.z) / 2,
        };
        return (
          <Fragment key={building.building_id || `building-${idx}`}>
        <BuildingBox
          building={building}
          isSelected={selected === building}
          onSelect={() => onSelect(building)}
        />
            {/* Labels for buildings (only if labelMode is "all") */}
            {labelMode === "all" && (
              <ObjectLabel
                position={[center.x, center.z, center.y]}
                text={building.building_id || `Building ${idx + 1}`}
                isHighlighted={highlightedId === building.building_id}
              />
            )}
          </Fragment>
        );
      })}

      {zones.map((zone, idx) => {
        // Try multiple matching strategies for zoneCostData
        const zoneCostData = zoneCostMap?.zones.find(z => 
          z.zone_name === zone.zone_name || 
          z.zone_name?.toLowerCase() === zone.zone_name?.toLowerCase() ||
          z.zone_id === zone.zone_name
        ) || null;
        
        // Get package data if in Packages mode
        const packageId = packageViewMode === "packages" ? workPackageMap?.zone_to_package[zone.zone_name] : undefined;
        const packageData = packageId ? workPackageMap?.packages.find(p => p.id === packageId) : undefined;
        
        const center = zone.bounding_box ? {
          x: (zone.bounding_box.min.x + zone.bounding_box.max.x) / 2,
          y: (zone.bounding_box.min.y + zone.bounding_box.max.y) / 2,
          z: (zone.bounding_box.min.z + zone.bounding_box.max.z) / 2,
        } : null;
        
        // Task 7: Determine label text with contractor-friendly labels
        const labelText = packageViewMode === "packages" && packageData
          ? formatPackageTitle(packageData.title)
          : `${getContractorLabel(zone.zone_name)}${zoneCostData && heatmapMode === "cost" ? ` $${zoneCostData.total_cost.toLocaleString()}` : ""}`;
        
        return (
          <Fragment key={zone.zone_name || `zone-${idx}`}>
        <ZoneBox
          zone={zone}
          isSelected={selected === zone}
          onSelect={() => {
            if (packageViewMode === "packages" && packageId && onSelectPackage) {
              onSelectPackage(packageId);
            } else {
              onSelect(zone);
            }
          }}
              heatmapMode={heatmapMode}
              zoneCostData={zoneCostData || null}
              maxCost={zoneCostMap?.max_cost || 0}
              minCost={zoneCostMap?.min_cost || 0}
              viewMode={packageViewMode}
              packageData={packageData || null}
              packageMaxCost={packageCostRange.max}
              packageMinCost={packageCostRange.min}
            />
            {/* Labels for zones (if labelMode is "zones" or "all") */}
            {center && (labelMode === "zones" || labelMode === "all") && (
              <ObjectLabel
                position={[center.x, center.z, center.y]}
                text={labelText}
                isHighlighted={highlightedId === zone.zone_name}
              />
            )}
          </Fragment>
        );
      })}

      {/* Cross-section regions (only in Section view) */}
      {viewMode === "section" && crossSectionRegions && crossSectionRegions.map((region, idx) => {
        const center = {
          x: (region.bounding_box.min.x + region.bounding_box.max.x) / 2,
          y: (region.bounding_box.min.y + region.bounding_box.max.y) / 2,
          z: (region.bounding_box.min.z + region.bounding_box.max.z) / 2,
        };
        return (
          <Fragment key={region.region_id || `region-${idx}`}>
            <CrossSectionRegionBox
              region={region}
              isSelected={selectedRegion?.region_id === region.region_id}
              onSelect={() => onSelectRegion(region)}
            />
            {/* Labels for regions (if labelMode is "all") */}
            {labelMode === "all" && (
              <ObjectLabel
                position={[center.x, center.z, center.y]}
                text={`${region.region_type} (${region.region_id})`}
                isHighlighted={highlightedId === region.region_id}
              />
            )}
          </Fragment>
        );
      })}

      {/* Task 4: Render ghost neighbors */}
      {ghostNeighbors && ghostNeighbors.map((neighbor) => {
        const dims = getBoundingBoxDimensions(neighbor.bounding_box);
        const center = {
          x: (neighbor.bounding_box.min.x + neighbor.bounding_box.max.x) / 2,
          y: (neighbor.bounding_box.min.y + neighbor.bounding_box.max.y) / 2,
          z: (neighbor.bounding_box.min.z + neighbor.bounding_box.max.z) / 2,
        };

        return (
          <Fragment key={neighbor.building_id}>
            <mesh
              position={[center.x, center.z, center.y]}
              onClick={(e) => e.stopPropagation()}
            >
              <boxGeometry args={[dims.width, dims.height, dims.depth]} />
              <meshStandardMaterial
                color="#999999"
                opacity={0.3}
                transparent={true}
                wireframe={false}
                side={THREE.DoubleSide}
                emissive="#333333"
                emissiveIntensity={0.1}
              />
            </mesh>
            {/* Always show ghost neighbor labels (important for context) */}
            <ObjectLabel
              position={[center.x, center.z + dims.height / 2 + 2, center.y]}
              text={`${neighbor.label}${neighbor.building_id === "adjacent_left" ? " (West)" : neighbor.building_id === "adjacent_right" ? " (East)" : ""}`}
            />
          </Fragment>
        );
      })}

      {/* Task 4: Render ground plane */}
      {groundPlane && (
        <mesh
          position={[groundPlane.center.x, 0, groundPlane.center.y]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[groundPlane.size, groundPlane.size]} />
          <meshStandardMaterial
            color="#d0d0d0"
            opacity={0.4}
            transparent={true}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Task 4: Render axis labels */}
      {axisLabels && axisLabels.map((axis, idx) => {
        const length = 20; // Label arrow length
        const origin = groundPlane?.center || { x: 0, y: 0, z: 0 };
        const end = {
          x: origin.x + axis.vector.x * length,
          y: origin.z + axis.vector.z * length,
          z: origin.y + axis.vector.y * length,
        };

        return (
          <Fragment key={`axis-${idx}`}>
            <line>
              <bufferGeometry>
                <bufferAttribute
                  attach="attributes-position"
                  count={2}
                  array={new Float32Array([
                    origin.x, origin.z, origin.y,
                    end.x, end.y, end.z,
                  ])}
                  itemSize={3}
                />
              </bufferGeometry>
              <lineBasicMaterial color="#666666" linewidth={3} />
            </line>
            {/* Always show axis labels (they're important for context) */}
            <ObjectLabel
              position={[end.x, end.y + 2, end.z]}
              text={axis.label}
            />
          </Fragment>
        );
      })}

      {/* Task 5: Render dimension HUD - positioned relative to scene bounds */}
      {dimensionHud && (() => {
        // Position HUD above the scene (calculate from buildings/zones)
        const sceneBbox = getSceneBoundingBox(buildings, zones);
        let hudY = 20; // Default
        if (sceneBbox) {
          hudY = sceneBbox.max.z + 5; // Above the tallest building
        }
        return (
          <Html position={[0, hudY, 0]} center style={{ pointerEvents: "none" }}>
            <div className="bg-black/95 text-white px-4 py-2.5 rounded-lg text-sm font-mono border-2 border-white/30 shadow-2xl backdrop-blur-sm">
              <div className="flex items-center gap-3">
                <span className="text-blue-300 font-bold">Building Dimensions:</span>
                <span className="font-bold text-white">
                  {dimensionHud.width_ft !== null ? `${dimensionHud.width_ft.toFixed(1)}'` : '?'} W
                </span>
                <span className="text-gray-400">×</span>
                <span className="font-bold text-white">
                  {dimensionHud.depth_ft !== null ? `${dimensionHud.depth_ft.toFixed(1)}'` : '?'} D
                </span>
                <span className="text-gray-400">×</span>
                <span className="font-bold text-white">
                  {dimensionHud.height_ft !== null ? `${dimensionHud.height_ft.toFixed(1)}'` : '?'} H
                </span>
              </div>
              {dimensionHud.confidence < 1.0 && (
                <div className="text-yellow-400 text-[10px] mt-1.5 italic">
                  {dimensionHud.provenance}
                </div>
              )}
            </div>
          </Html>
        );
      })()}

      <OrbitControls
        ref={controlsRef}
        makeDefault
        enabled={true}
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        enableDamping={false}
        minDistance={5}
        maxDistance={500}
        rotateSpeed={1.0}
        zoomSpeed={1.0}
        panSpeed={1.0}
        screenSpacePanning={false}
      />
    </>
  );
}

// Detail Overlay Panel component
function DetailOverlayPanel({
  selectedRegion,
  detailOverlayIndex,
  onClose,
}: {
  selectedRegion: CrossSectionRegion | null;
  detailOverlayIndex?: DetailOverlayIndex | null;
  onClose: () => void;
}) {
  if (!selectedRegion) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Detail Overlay</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Select a cross-section region to view linked details and evidence.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Find matching region in detailOverlayIndex
  const overlayData = detailOverlayIndex?.regions.find(
    (r) => r.region_id === selectedRegion.region_id
  );

  return (
    <Card className="h-full overflow-y-auto">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>
              {selectedRegion.region_type.replace(/_/g, " ")} • {selectedRegion.region_id}
            </CardTitle>
            <CardDescription className="mt-1">
              Cross-section region
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Detail References */}
        {overlayData && overlayData.detail_refs.length > 0 ? (
          <div>
            <h4 className="text-sm font-semibold mb-2">Detail References</h4>
            <div className="space-y-2">
              {overlayData.detail_refs.map((detail, idx) => (
                <div key={idx} className="border rounded p-2 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="secondary" className="font-mono">
                      {detail.sheet_id}
                    </Badge>
                    <span className="font-medium">{detail.detail_label}</span>
                  </div>
                  <div className="text-muted-foreground">
                    <span className="font-mono">{detail.detail_id}</span>
                    {detail.detail_type && (
                      <span className="ml-2">• {detail.detail_type.replace(/_/g, " ")}</span>
                    )}
                  </div>
                  <div className="text-muted-foreground mt-1">
                    Page {detail.page_number}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : overlayData && overlayData.detail_ids.length > 0 ? (
          <div>
            <h4 className="text-sm font-semibold mb-2">Detail References</h4>
            <div className="space-y-1">
              {overlayData.detail_ids.map((detailId, idx) => (
                <Badge key={idx} variant="outline" className="mr-2">
                  {detailId}
                </Badge>
              ))}
            </div>
          </div>
        ) : (
          <div>
            <h4 className="text-sm font-semibold mb-2">Detail References</h4>
            <p className="text-sm text-muted-foreground">
              No linked details found for this region.
            </p>
          </div>
        )}

        {/* Evidence Pages */}
        {overlayData && overlayData.evidence_pages.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2">Evidence Pages</h4>
            <div className="flex flex-wrap gap-2">
              {overlayData.evidence_pages.map((pageNum, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  className="font-mono"
                >
                  Page {pageNum}
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* Evidence Snippets */}
        {overlayData && overlayData.snippets.length > 0 ? (
          <div>
            <h4 className="text-sm font-semibold mb-2">Evidence Snippets</h4>
            <div className="space-y-2">
              {overlayData.snippets.map((snippet, idx) => (
                <div key={idx} className="border rounded p-2 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="outline" className="font-mono">
                      Page {snippet.page_number}
                    </Badge>
                    {snippet.sheet_id && (
                      <Badge variant="secondary" className="font-mono text-xs">
                        {snippet.sheet_id}
                      </Badge>
                    )}
                    {snippet.location_type && (
                      <Badge variant="outline" className="text-xs">
                        {snippet.location_type}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground mt-1">
                    {snippet.snippet.length > 200
                      ? `${snippet.snippet.substring(0, 200)}...`
                      : snippet.snippet}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          overlayData && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Evidence Snippets</h4>
              <p className="text-sm text-muted-foreground">
                No evidence snippets available.
              </p>
            </div>
          )
        )}

        {/* Empty state if no overlay data */}
        {!overlayData && (
          <div className="text-sm text-muted-foreground">
            No detail overlay data available for this region.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Work Package Panel component (Task 2)
function WorkPackagePanel({
  packageId,
  workPackageMap,
  bidItems,
  projectId,
  onClose,
}: {
  packageId: string;
  workPackageMap: WorkPackageMap | null;
  bidItems?: BidLineItem[];
  projectId: string;
  onClose: () => void;
}) {
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedItemIndex, setSelectedItemIndex] = useState<number | null>(null);
  const [showZones, setShowZones] = useState(false);
  const { getEvidenceForBidItem } = useEvidenceIndex(projectId);

  const packageData = workPackageMap?.packages.find(p => p.id === packageId);

  if (!packageData) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Package Not Found</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Package {packageId} not found in work package map.</p>
          <Button variant="outline" size="sm" onClick={onClose} className="mt-4">
            Close
          </Button>
        </CardContent>
      </Card>
    );
  }

  const packageLineItems = packageData.member_line_item_ids
    .map(id => {
      const idx = parseInt(id, 10);
      if (isNaN(idx) || !bidItems || idx >= bidItems.length) return null;
      return { index: idx, item: bidItems[idx] };
    })
    .filter((item): item is { index: number; item: BidLineItem } => item !== null);

  return (
    <Card className="h-full overflow-y-auto">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="text-lg">{formatPackageTitle(packageData.title)}</CardTitle>
          <CardDescription className="mt-1">
            {packageData.division} {packageData.trade && `• ${packageData.trade}`}
          </CardDescription>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total Cost */}
        <div>
          <h4 className="text-sm font-semibold mb-1">Package Cost</h4>
          <div className="text-2xl font-bold">
            ${packageData.estimated_cost.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant={packageData.priority === "high" ? "destructive" : packageData.priority === "medium" ? "default" : "secondary"}>
              {packageData.priority} priority
            </Badge>
            <Badge variant="outline" className="text-xs">
              {Math.round(packageData.confidence * 100)}% confidence
            </Badge>
            {/* Task 6: "Review" badge for low confidence */}
            {packageData.confidence < 0.4 && (
              <Badge variant="destructive" className="text-xs">
                Review
              </Badge>
            )}
          </div>
        </div>

        {/* Included Bid Line Items */}
        {packageLineItems.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <h4 className="text-sm font-semibold">Included Bid Line Items ({packageLineItems.length})</h4>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {packageLineItems.map(({ index, item }) => (
                <div key={index} className="text-xs border rounded p-2">
                  <div className="flex justify-between items-start mb-1">
                    <div className="font-medium flex-1">{item.description}</div>
                    <div className="text-right ml-2">
                      <div className="font-semibold">
                        ${item.total_cost?.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        }) || "0.00"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <Badge variant="secondary" className="text-xs">
                      {item.division}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs"
                      onClick={() => {
                        setSelectedItemIndex(index);
                        setEvidenceDrawerOpen(true);
                      }}
                    >
                      <FileText className="h-3 w-3 mr-1" />
                      Evidence
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Member Zones (collapsed by default) */}
        {packageData.member_zone_ids.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <button
              onClick={() => setShowZones(!showZones)}
              className="flex items-center justify-between w-full text-left"
            >
              <h4 className="text-sm font-semibold">
                Member Zones ({packageData.member_zone_ids.length})
              </h4>
              <span className="text-xs text-muted-foreground">{showZones ? "Hide" : "Show"}</span>
            </button>
            {showZones && (
              <div className="space-y-1">
                {packageData.member_zone_ids.map((zoneId, idx) => (
                  <div key={idx} className="text-xs p-2 bg-muted rounded">
                    {zoneId}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Basis References */}
        {packageData.basis_refs.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <h4 className="text-sm font-semibold">Basis References</h4>
            <div className="flex flex-wrap gap-2">
              {packageData.basis_refs.map((ref, idx) => (
                <Badge key={idx} variant="outline" className="font-mono text-xs">
                  {ref}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>

      {/* Evidence Drawer for line items */}
      {selectedItemIndex !== null && (
        <EvidenceDrawer
          open={evidenceDrawerOpen}
          onOpenChange={(open) => {
            setEvidenceDrawerOpen(open);
            if (!open) setSelectedItemIndex(null);
          }}
          title={packageLineItems.find(({ index }) => index === selectedItemIndex)?.item.description || "Evidence"}
          projectId={projectId}
          subtitle={`Line item ${selectedItemIndex + 1}`}
          evidence={getEvidenceForBidItem(selectedItemIndex)}
        />
      )}
    </Card>
  );
}

// Inspection panel component
function InspectionPanel({
  selected,
  bidItems,
  projectId,
  zoneCostMap,
  onClose,
  onResetView,
}: {
  selected: Building | Zone | null;
  bidItems?: BidLineItem[];
  projectId: string;
  zoneCostMap?: ZoneCostMap | null;
  onClose: () => void;
  onResetView: () => void;
}) {
  // ALL HOOKS MUST BE CALLED BEFORE ANY CONDITIONAL RETURNS
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [selectedItemIndex, setSelectedItemIndex] = useState<number | null>(null);
  const { getEvidenceForZone, getEvidenceForBidItem } = useEvidenceIndex(projectId);
  
  // useMemo must be called unconditionally (before early return)
  const linkedBidItems = useMemo(() => {
    if (!bidItems || !selected) return [];
    const isBuilding = "building_type" in selected;
    const zoneName = isBuilding ? selected.building_id || "" : selected.zone_name;
    return findLinkedBidItems(zoneName, bidItems);
  }, [selected, bidItems]);
  
  // Early return AFTER all hooks
  if (!selected) return null;

  const isBuilding = "building_type" in selected;
  
  // Get zone cost data if available
  const zoneCostData = !isBuilding && zoneCostMap
    ? zoneCostMap.zones.find(z => z.zone_name === selected.zone_name)
    : null;
  const bbox = isBuilding
    ? selected.bounding_box
    : selected.bounding_box || null;

  const dims = bbox ? getBoundingBoxDimensions(bbox) : null;
  const footprint = bbox ? getFootprintArea(bbox) : null;
  const volume = bbox ? getVolume(bbox) : null;

  return (
    <Card className="h-full overflow-y-auto">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-lg">
          {isBuilding
            ? `Building: ${selected.building_id || "Unknown"}`
            : selected.zone_name}
        </CardTitle>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onResetView}>
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isBuilding && selected.zone_type && (
          <div>
            <span className="text-sm font-medium">Zone Type: </span>
            <Badge variant="secondary">{selected.zone_type}</Badge>
          </div>
        )}

        {isBuilding && (
          <div>
            <span className="text-sm font-medium">Building Type: </span>
            <Badge variant="secondary">{selected.building_type}</Badge>
          </div>
        )}

        {dims && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Dimensions</h4>
            <div className="text-sm space-y-1">
              <div>Width: {dims.width.toFixed(1)} ft</div>
              <div>Depth: {dims.depth.toFixed(1)} ft</div>
              <div>Height: {dims.height.toFixed(1)} ft</div>
            </div>
          </div>
        )}

        {footprint !== null && (
          <div>
            <span className="text-sm font-medium">Footprint: </span>
            <span className="text-sm">{footprint.toFixed(0)} SF</span>
          </div>
        )}

        {volume !== null && (
          <div>
            <span className="text-sm font-medium">Volume: </span>
            <span className="text-sm">{volume.toFixed(0)} CF</span>
          </div>
        )}

        {(!isBuilding && selected.page_number) && (
          <div>
            <span className="text-sm font-medium">Page: </span>
            <span className="text-sm">{selected.page_number}</span>
          </div>
        )}

        {/* Evidence button */}
        {!isBuilding && (
          <div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEvidenceDrawerOpen(true)}
              className="w-full flex items-center gap-2"
            >
              <FileText className="h-4 w-4" />
              View Evidence
            </Button>
                    </div>
        )}

        {selected.evidence && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Evidence</h4>
            <p className="text-xs text-muted-foreground bg-muted p-2 rounded">
              {selected.evidence.length > 200
                ? `${selected.evidence.substring(0, 200)}...`
                : selected.evidence}
            </p>
          </div>
        )}

        {!selected.evidence && (
          <div className="text-xs text-muted-foreground">
            Evidence not available
          </div>
        )}

        {/* Zone Cost Breakdown (Phase 8.3) */}
        {!isBuilding && zoneCostData && (
          <div className="space-y-3 border-t pt-3">
            <div>
              <h4 className="text-sm font-semibold mb-1">Zone Cost</h4>
              <div className="text-lg font-bold">
                ${zoneCostData.total_cost.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
              <Badge variant="outline" className="text-xs mt-1">
                {zoneCostData.attribution_method.replace(/_/g, " ")}
              </Badge>
            </div>

            {zoneCostData.top_line_items.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">Top Contributing Items</h4>
                <div className="space-y-2">
                  {zoneCostData.top_line_items.map((item, idx) => (
                    <div key={idx} className="text-xs border rounded p-2">
                      <div className="flex justify-between items-start mb-1">
                        <div className="font-medium flex-1">{item.title}</div>
                        <div className="text-right ml-2">
                          <div className="font-semibold">
                            ${item.total_cost.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </div>
                          <div className="text-muted-foreground">
                            {item.contribution_percent.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <Badge variant="secondary" className="text-xs">
                          {item.division}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs"
                          onClick={() => {
                            setSelectedItemIndex(item.line_item_index);
                            setEvidenceDrawerOpen(true);
                          }}
                        >
                          <FileText className="h-3 w-3 mr-1" />
                          Evidence
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {Object.keys(zoneCostData.division_breakdown).length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">By Division</h4>
                <div className="space-y-1">
                  {Object.entries(zoneCostData.division_breakdown)
                    .sort(([, a], [, b]) => b - a)
                    .map(([division, cost]) => (
                      <div key={division} className="flex justify-between text-xs">
                        <span>{division}</span>
                        <span className="font-mono">
                          ${cost.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        )}

        {linkedBidItems.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Linked Bid Items</h4>
            <div className="space-y-2">
              {linkedBidItems.slice(0, 5).map((item, idx) => (
                <div key={idx} className="text-xs border rounded p-2">
                  <div className="font-medium">{item.description}</div>
                  <div className="text-muted-foreground">
                    {item.division} • ${item.total_cost.toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>

      {/* Evidence Drawer */}
      {!isBuilding && (
        <>
          <EvidenceDrawer
            open={evidenceDrawerOpen && selectedItemIndex === null}
            onOpenChange={setEvidenceDrawerOpen}
            title={`Zone — ${selected.zone_name}`}
            subtitle={selected.zone_type ? `Type: ${selected.zone_type}` : undefined}
            evidence={getEvidenceForZone(selected.zone_name)}
            projectId={projectId}
            initialPage={(() => {
              const zoneEvidence = getEvidenceForZone(selected.zone_name);
              return zoneEvidence.length > 0 ? zoneEvidence[0].page_number : undefined;
            })()}
          />
          {selectedItemIndex !== null && zoneCostData && (
            <EvidenceDrawer
              open={evidenceDrawerOpen}
              onOpenChange={(open) => {
                setEvidenceDrawerOpen(open);
                if (!open) setSelectedItemIndex(null);
              }}
              title={zoneCostData.top_line_items.find(item => item.line_item_index === selectedItemIndex)?.title || "Evidence"}
              projectId={projectId}
              subtitle={`Line item ${selectedItemIndex + 1}`}
              evidence={getEvidenceForBidItem(selectedItemIndex)}
            />
          )}
        </>
      )}
    </Card>
  );
}

export function ModelViewer3D({
  buildings,
  zones,
  bidItems,
  projectId,
  zoneCostMap,
  detailOverlayIndex,
  workPackageMap,
  crossSectionRegions,
  ghostNeighbors,
  groundPlane,
  axisLabels,
  dimensionHud,
  onSelectionChange,
  onSearchSelectRef,
}: ModelViewer3DProps) {
  const [selected, setSelected] = useState<Building | Zone | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<CrossSectionRegion | null>(null);
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [heatmapMode, setHeatmapMode] = useState<"none" | "cost" | "division">("none");
  const [viewMode, setViewMode] = useState<"normal" | "section">("normal");
  const [packageViewMode, setPackageViewMode] = useState<"zones" | "packages">("zones"); // Task 2: Zones vs Packages
  const [labelMode, setLabelMode] = useState<"off" | "zones" | "all">("zones"); // Phase 9: Default to showing zone labels
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const controlsRef = useRef<any>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const viewerContainerRef = useRef<HTMLDivElement>(null);

  const handleSelectRegion = (region: CrossSectionRegion | null) => {
    setSelectedRegion(region);
    // Clear zone/building selection when selecting a region
    if (region) {
      setSelected(null);
    }
  };

  const handleSelect = (item: Building | Zone | null) => {
    setSelected(item);
    // Clear region and package selection when selecting a zone/building
    if (item) {
      setSelectedRegion(null);
      setSelectedPackageId(null);
    }
    onSelectionChange?.(item);
  };

  const handleSelectPackage = (packageId: string | null) => {
    setSelectedPackageId(packageId);
    // Clear zone/building selection when selecting a package
    if (packageId) {
      setSelected(null);
      setSelectedRegion(null);
    }
  };

  const handleResetView = () => {
    if (controlsRef.current) {
      // Reset camera to auto-frame position
      const sceneBbox = getSceneBoundingBox(buildings, zones);
      if (sceneBbox) {
        const dims = getBoundingBoxDimensions(sceneBbox);
        const center = {
          x: (sceneBbox.min.x + sceneBbox.max.x) / 2,
          y: (sceneBbox.min.y + sceneBbox.max.y) / 2,
          z: (sceneBbox.min.z + sceneBbox.max.z) / 2,
        };
        const maxDim = Math.max(dims.width, dims.depth, dims.height);
        const distance = maxDim * 2.5;
        controlsRef.current.object.position.set(
          center.x + distance,
          center.z + distance * 0.7,
          center.y + distance
        );
        controlsRef.current.target.set(center.x, center.z, center.y);
        controlsRef.current.update();
      }
    }
  };

  // Focus target handler for search (Phase 8.5)
  const focusTarget = useMemo(() => {
    return (entry: SearchEntry) => {
      if (!controlsRef.current) return;

      // Get camera from controls
      const camera = controlsRef.current.object as THREE.PerspectiveCamera;
      if (!camera) return;

      // Pulse highlight
      setHighlightedId(entry.id);
      setTimeout(() => setHighlightedId(null), 2000);

      // Handle different target types
      if (entry.target.type === "bbox" && entry.target.bbox) {
        const focus = computeFocusFromBBox(entry.target.bbox);
        flyTo(camera, controlsRef.current, focus, 650);
        
        // Select appropriate item
        if (entry.type === "building" && entry.target.building_id) {
          const building = buildings.find(b => b.building_id === entry.target.building_id);
          if (building) {
            handleSelect(building);
          }
        } else if (entry.type === "zone" && entry.target.zone_name) {
          const zone = zones.find(z => z.zone_name === entry.target.zone_name);
          if (zone) {
            handleSelect(zone);
          }
        } else if (entry.type === "region" && entry.target.region_id) {
          const region = crossSectionRegions?.find(r => r.region_id === entry.target.region_id);
          if (region) {
            setViewMode("section");
            handleSelectRegion(region);
          }
        }
      } else if (entry.target.type === "bid_item" && entry.target.bid_item_index !== undefined) {
        // For bid items, try to find linked zone via evidence_index
        // This is a simplified implementation - full linking would use evidence_index
        if (zones.length > 0) {
          handleSelect(zones[0]);
        }
      } else if (entry.target.type === "detail" && entry.target.region_id) {
        // Switch to section mode and select region
        setViewMode("section");
        const region = crossSectionRegions?.find(r => r.region_id === entry.target.region_id);
        if (region) {
          handleSelectRegion(region);
        }
      }
    };
  }, [buildings, zones, crossSectionRegions]);

  // Register search handler
  useEffect(() => {
    if (onSearchSelectRef) {
      onSearchSelectRef(focusTarget);
    }
  }, [onSearchSelectRef, focusTarget]);

  const toggleFullscreen = async () => {
    if (!viewerContainerRef.current) return;
    
    try {
      if (!isFullscreen) {
        // Enter fullscreen
        if (viewerContainerRef.current.requestFullscreen) {
          await viewerContainerRef.current.requestFullscreen();
        } else if ((viewerContainerRef.current as any).webkitRequestFullscreen) {
          await (viewerContainerRef.current as any).webkitRequestFullscreen();
        } else if ((viewerContainerRef.current as any).mozRequestFullScreen) {
          await (viewerContainerRef.current as any).mozRequestFullScreen();
        } else if ((viewerContainerRef.current as any).msRequestFullscreen) {
          await (viewerContainerRef.current as any).msRequestFullscreen();
        }
        setIsFullscreen(true);
      } else {
        // Exit fullscreen
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        } else if ((document as any).webkitExitFullscreen) {
          await (document as any).webkitExitFullscreen();
        } else if ((document as any).mozCancelFullScreen) {
          await (document as any).mozCancelFullScreen();
        } else if ((document as any).msExitFullscreen) {
          await (document as any).msExitFullscreen();
        }
        setIsFullscreen(false);
      }
    } catch (err) {
      console.error("Fullscreen error:", err);
      // Fallback to CSS-based fullscreen
      setIsFullscreen(!isFullscreen);
    }
  };

  // Listen for fullscreen changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isCurrentlyFullscreen = !!(
        document.fullscreenElement ||
        (document as any).webkitFullscreenElement ||
        (document as any).mozFullScreenElement ||
        (document as any).msFullscreenElement
      );
      setIsFullscreen(isCurrentlyFullscreen);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("mozfullscreenchange", handleFullscreenChange);
    document.addEventListener("MSFullscreenChange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("webkitfullscreenchange", handleFullscreenChange);
      document.removeEventListener("mozfullscreenchange", handleFullscreenChange);
      document.removeEventListener("MSFullscreenChange", handleFullscreenChange);
    };
  }, []);

  return (
      <div 
        ref={viewerContainerRef}
        className={`${isFullscreen ? "fixed inset-0 z-50 bg-gray-900 flex flex-col" : "space-y-4"}`}
        style={{ pointerEvents: "auto" }}
      >
      {/* View Mode and Heatmap Toggles */}
      <div className={`flex items-center gap-4 p-2 border rounded-lg ${isFullscreen ? "bg-gray-800 border-gray-700" : "bg-gray-50"}`}>
        {/* Task 2: Zones vs Packages Toggle */}
        {workPackageMap && workPackageMap.packages.length > 0 && (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">View Mode:</span>
              <div className="flex gap-2">
                <Button
                  variant={packageViewMode === "zones" ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setPackageViewMode("zones");
                    setSelectedPackageId(null);
                  }}
                >
                  Zones
                </Button>
                <Button
                  variant={packageViewMode === "packages" ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setPackageViewMode("packages");
                    setSelected(null);
                  }}
                >
                  Packages
                </Button>
              </div>
            </div>
            <Separator orientation="vertical" className="h-6" />
          </>
        )}

        {/* View Mode Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">View:</span>
          <div className="flex gap-2">
            <Button
              variant={viewMode === "normal" ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setViewMode("normal");
                setSelectedRegion(null);
              }}
            >
              Normal
            </Button>
            <Button
              variant={viewMode === "section" ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setViewMode("section");
                setSelected(null);
              }}
              disabled={!crossSectionRegions || crossSectionRegions.length === 0}
            >
              Section
            </Button>
          </div>
        </div>

        {/* Heatmap Toggle (only in Normal view, Zones mode) */}
        {zoneCostMap && viewMode === "normal" && packageViewMode === "zones" && (
          <>
            <Separator orientation="vertical" className="h-6" />
            <span className="text-sm font-medium">Heatmap:</span>
            <div className="flex gap-2">
              <Button
                variant={heatmapMode === "none" ? "default" : "outline"}
                size="sm"
                onClick={() => setHeatmapMode("none")}
              >
                None
              </Button>
              <Button
                variant={heatmapMode === "cost" ? "default" : "outline"}
                size="sm"
                onClick={() => setHeatmapMode("cost")}
              >
                Cost
              </Button>
              <Button
                variant={heatmapMode === "division" ? "default" : "outline"}
                size="sm"
                onClick={() => setHeatmapMode("division")}
              >
                Division
              </Button>
            </div>
            {heatmapMode === "cost" && zoneCostMap.max_cost > 0 && (
              <div className="ml-auto flex items-center gap-2 text-xs">
                <span className="text-gray-600">Range:</span>
                <span className="font-mono">${zoneCostMap.min_cost.toLocaleString()}</span>
                <span>→</span>
                <span className="font-mono">${zoneCostMap.max_cost.toLocaleString()}</span>
              </div>
            )}
          </>
        )}
        
        {/* Labels Toggle */}
        <Separator orientation="vertical" className="h-6" />
        <span className="text-sm font-medium">Labels:</span>
        <div className="flex gap-2">
          <Button
            variant={labelMode === "off" ? "default" : "outline"}
            size="sm"
            onClick={() => setLabelMode("off")}
          >
            Off
          </Button>
          <Button
            variant={labelMode === "zones" ? "default" : "outline"}
            size="sm"
            onClick={() => setLabelMode("zones")}
          >
            Zones
          </Button>
          <Button
            variant={labelMode === "all" ? "default" : "outline"}
            size="sm"
            onClick={() => setLabelMode("all")}
          >
            All
          </Button>
        </div>
        
        {/* Fullscreen Toggle */}
        <Button
          variant="outline"
          size="sm"
          onClick={toggleFullscreen}
          className="ml-auto"
        >
          {isFullscreen ? (
            <>
              <Minimize2 className="h-4 w-4 mr-1" />
              Exit Fullscreen
            </>
          ) : (
            <>
              <Maximize2 className="h-4 w-4 mr-1" />
              Fullscreen
            </>
          )}
        </Button>
      </div>
      
      <div className={`flex gap-4 flex-1 ${isFullscreen ? "p-4" : ""}`}>
        <div 
          className={`flex-1 relative border rounded-lg overflow-hidden bg-gray-900 ${isFullscreen ? "h-full" : "h-[600px]"}`}
          style={{ touchAction: "none" }}
          onContextMenu={(e) => e.preventDefault()}
        >
        <Suspense fallback={<div className="absolute inset-0 flex items-center justify-center text-white">Loading 3D viewer...</div>}>
            <Canvas
              style={{ width: "100%", height: "100%", display: "block", touchAction: "none" }}
              gl={{ preserveDrawingBuffer: true, alpha: false, antialias: true, powerPreference: "high-performance" }}
              dpr={[1, 2]}
              frameloop="always"
              onCreated={({ gl, camera }) => {
                // Store camera reference
                if (cameraRef.current !== camera) {
                  cameraRef.current = camera as THREE.PerspectiveCamera;
                }
                
                // Handle WebGL context loss
                const canvas = gl.domElement;
                const handleContextLost = (e: Event) => {
                  e.preventDefault();
                  console.warn("[3D Viewer] WebGL context lost");
                };
                const handleContextRestored = () => {
                  console.log("[3D Viewer] WebGL context restored");
                };
                
                canvas.addEventListener("webglcontextlost", handleContextLost);
                canvas.addEventListener("webglcontextrestored", handleContextRestored);
                
                // Debug: Log pointer events
                if (process.env.NODE_ENV === "development") {
                  const logEvent = (type: string) => (e: Event) => {
                    console.log(`[Canvas ${type}]`, e.type, e);
                  };
                  canvas.addEventListener("pointerdown", logEvent("pointerdown"));
                  canvas.addEventListener("wheel", logEvent("wheel"));
                  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
                }
              }}
            >
            <Scene3D
              buildings={buildings}
              zones={zones}
              selected={selected}
              onSelect={handleSelect}
              controlsRef={controlsRef}
              heatmapMode={heatmapMode}
              zoneCostMap={zoneCostMap}
              viewMode={viewMode}
              crossSectionRegions={crossSectionRegions}
              selectedRegion={selectedRegion}
              onSelectRegion={handleSelectRegion}
              labelMode={labelMode}
              highlightedId={highlightedId}
              cameraRef={cameraRef}
              packageViewMode={packageViewMode}
              workPackageMap={workPackageMap || null}
              onSelectPackage={handleSelectPackage}
              ghostNeighbors={ghostNeighbors}
              groundPlane={groundPlane}
              axisLabels={axisLabels}
              dimensionHud={dimensionHud}
            />
          </Canvas>
        </Suspense>
      </div>
        {!isFullscreen && (
      <div className="w-[30%] min-w-[300px]">
            {viewMode === "section" ? (
            <DetailOverlayPanel
              selectedRegion={selectedRegion}
              detailOverlayIndex={detailOverlayIndex || null}
              onClose={() => handleSelectRegion(null)}
            />
          ) : packageViewMode === "packages" && selectedPackageId ? (
            <WorkPackagePanel
              packageId={selectedPackageId}
              workPackageMap={workPackageMap || null}
              bidItems={bidItems}
              projectId={projectId}
              onClose={() => handleSelectPackage(null)}
            />
          ) : (
        <InspectionPanel
          selected={selected}
          bidItems={bidItems}
              projectId={projectId}
              zoneCostMap={zoneCostMap}
          onClose={() => handleSelect(null)}
          onResetView={handleResetView}
        />
          )}
          </div>
        )}
      </div>
    </div>
  );
}

