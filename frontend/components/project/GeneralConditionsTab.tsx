"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { AlertCircle, Loader2, Building2, FileCheck, Shield, ClipboardList } from "lucide-react";

interface GeneralConditionsItem {
  category: string;
  title: string;
  description: string | null;
  quantity: number;
  unit: string;
  unit_cost: number;
  total_cost: number;
  basis: string;
}

interface GeneralConditions {
  project_id: string;
  building_type: string;
  building_height_ft: number | null;
  region: string;
  estimated_duration_weeks: number | null;
  items: GeneralConditionsItem[];
  total_cost: number;
  generated_at: string;
}

interface GeneralConditionsTabProps {
  projectId: string;
}

export function GeneralConditionsTab({ projectId }: GeneralConditionsTabProps) {
  // Use projectId prop or fallback to useParams for backwards compatibility
  const params = useParams();
  const effectiveProjectId = projectId || (params?.projectId as string);
  
  const [gc, setGc] = useState<GeneralConditions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadGC = async () => {
      try {
        const data = await api.getArtifact<GeneralConditions>(effectiveProjectId, "general_conditions");
        setGc(data);
        setError(null);
      } catch (err) {
        console.error("Failed to load general conditions:", err);
        setError("Failed to load general conditions");
      } finally {
        setLoading(false);
      }
    };

    if (effectiveProjectId) {
      loadGC();
    }
  }, [effectiveProjectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error || !gc) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          {error || "General conditions not available for this project"}
        </AlertDescription>
      </Alert>
    );
  }

  // Group items by category
  const itemsByCategory: Record<string, GeneralConditionsItem[]> = {};
  gc.items.forEach((item) => {
    if (!itemsByCategory[item.category]) {
      itemsByCategory[item.category] = [];
    }
    itemsByCategory[item.category].push(item);
  });

  const categoryIcons: Record<string, any> = {
    project_management: Building2,
    site_protection: Shield,
    temporary_facilities: Building2,
    utilities: ClipboardList,
    cleanup: ClipboardList,
    safety_equipment: Shield,
    permits: FileCheck,
    inspections: FileCheck,
    mobilization: Building2,
    security: Shield,
  };

  const categoryLabels: Record<string, string> = {
    project_management: "Project Management",
    site_protection: "Site Protection",
    temporary_facilities: "Temporary Facilities",
    utilities: "Utilities",
    cleanup: "Cleanup",
    safety_equipment: "Safety Equipment",
    permits: "Permits",
    inspections: "Inspections",
    mobilization: "Mobilization",
    security: "Security",
  };

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            General Conditions Summary
          </CardTitle>
          <CardDescription>
            Project-level overhead, logistics, and compliance costs
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <p className="text-sm text-gray-500">Building Type</p>
              <p className="text-lg font-semibold">{gc.building_type}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Height</p>
              <p className="text-lg font-semibold">
                {gc.building_height_ft !== null ? `${gc.building_height_ft} ft` : "N/A"}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Region</p>
              <p className="text-lg font-semibold">{gc.region}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Duration</p>
              <p className="text-lg font-semibold">
                {gc.estimated_duration_weeks !== null ? `${gc.estimated_duration_weeks} weeks` : "N/A"}
              </p>
            </div>
          </div>
          <div className="border-t pt-4">
            <div className="flex items-center justify-between">
              <span className="text-lg font-semibold">Total General Conditions</span>
              <span className="text-3xl font-bold">
                ${gc.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Items by Category */}
      {Object.entries(itemsByCategory).map(([category, items]) => {
        const Icon = categoryIcons[category] || ClipboardList;
        const categoryLabel = categoryLabels[category] || category;
        const categoryTotal = items.reduce((sum, item) => sum + item.total_cost, 0);

        return (
          <Card key={category}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Icon className="h-5 w-5" />
                {categoryLabel}
              </CardTitle>
              <CardDescription>
                {items.length} item{items.length !== 1 ? "s" : ""} • 
                Total: ${categoryTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Quantity</TableHead>
                    <TableHead>Unit Cost</TableHead>
                    <TableHead>Total Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item, idx) => (
                    <TableRow key={idx}>
                      <TableCell className="font-medium">{item.title}</TableCell>
                      <TableCell className="text-gray-600 text-sm">
                        {item.description || (
                          <span className="italic text-gray-400">No description</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {item.quantity} {item.unit}
                      </TableCell>
                      <TableCell>
                        ${item.unit_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="font-medium">
                        ${item.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </TableCell>
                    </TableRow>
                  ))}
                  {/* Category Total Row */}
                  <TableRow className="bg-gray-50 font-semibold">
                    <TableCell colSpan={4} className="text-right">
                      {categoryLabel} Total:
                    </TableCell>
                    <TableCell>
                      ${categoryTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

