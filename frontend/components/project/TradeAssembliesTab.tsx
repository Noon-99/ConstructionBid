"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { api } from "@/lib/api";
import { AlertCircle, Loader2, Package, Wrench, Users, Wrench as Tool } from "lucide-react";

interface TradeComponent {
  name: string;
  unit: string;
  qty: number;
  unit_cost: number | null;
  total_cost: number;
  cost_source: string;
  basis: string;
}

interface LaborComponent {
  trade: string;
  crew: string[];
  hours: number;
  rate: number | null;
  total_cost: number;
  basis: string;
}

interface EquipmentComponent {
  name: string;
  unit: string;
  qty: number;
  unit_cost: number | null;
  total_cost: number;
  basis: string;
}

interface TradeAssembly {
  id: string;
  title: string;
  division: string;
  unit: string;
  quantity: number;
  related_bid_item_ids: string[];
  components: TradeComponent[];
  labor: LaborComponent[];
  equipment: EquipmentComponent[];
  assumptions: string[];
  spec_refs: string[];
  evidence_refs: any[];
  ruleset_used: string;
}

interface TradeAssembliesResult {
  project_id: string;
  assemblies: TradeAssembly[];
  version: string;
  generated_at: string;
}

interface TradeAssembliesTabProps {
  projectId: string;
}

export function TradeAssembliesTab({ projectId }: TradeAssembliesTabProps) {
  // Use projectId prop or fallback to useParams for backwards compatibility
  const params = useParams();
  const effectiveProjectId = projectId || (params?.projectId as string);
  
  const [assemblies, setAssemblies] = useState<TradeAssembliesResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadAssemblies = async () => {
      try {
        const data = await api.getArtifact<TradeAssembliesResult>(effectiveProjectId, "trade_assemblies");
        setAssemblies(data);
        setError(null);
      } catch (err) {
        console.error("Failed to load trade assemblies:", err);
        setError("Failed to load trade assemblies");
      } finally {
        setLoading(false);
      }
    };

    if (effectiveProjectId) {
      loadAssemblies();
    }
  }, [effectiveProjectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error || !assemblies || assemblies.assemblies.length === 0) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          {error || "Trade assemblies not available for this project"}
        </AlertDescription>
      </Alert>
    );
  }

  // Calculate totals
  const totalMaterialCost = assemblies.assemblies.reduce(
    (sum, asm) => sum + asm.components.reduce((s, c) => s + c.total_cost, 0),
    0
  );
  const totalLaborCost = assemblies.assemblies.reduce(
    (sum, asm) => sum + asm.labor.reduce((s, l) => s + l.total_cost, 0),
    0
  );
  const totalEquipmentCost = assemblies.assemblies.reduce(
    (sum, asm) => sum + asm.equipment.reduce((s, e) => s + e.total_cost, 0),
    0
  );
  const grandTotal = totalMaterialCost + totalLaborCost + totalEquipmentCost;

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            Trade Assemblies Summary
          </CardTitle>
          <CardDescription>
            Detailed material, labor, and equipment breakdowns ({assemblies.assemblies.length} assemblies)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-500">Materials</p>
              <p className="text-2xl font-bold">${totalMaterialCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Labor</p>
              <p className="text-2xl font-bold">${totalLaborCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Equipment</p>
              <p className="text-2xl font-bold">${totalEquipmentCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Total</p>
              <p className="text-2xl font-bold">${grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Assemblies */}
      <Accordion type="single" collapsible className="space-y-4">
        {assemblies.assemblies.map((assembly) => {
          const assemblyMaterialCost = assembly.components.reduce((s, c) => s + c.total_cost, 0);
          const assemblyLaborCost = assembly.labor.reduce((s, l) => s + l.total_cost, 0);
          const assemblyEquipmentCost = assembly.equipment.reduce((s, e) => s + e.total_cost, 0);
          const assemblyTotal = assemblyMaterialCost + assemblyLaborCost + assemblyEquipmentCost;

          return (
            <Card key={assembly.id}>
              <AccordionItem value={assembly.id} className="border-none">
                <AccordionTrigger className="px-6 py-4 hover:no-underline">
                  <div className="flex items-center justify-between w-full mr-4">
                    <div className="text-left">
                      <h3 className="font-semibold text-lg">{assembly.title}</h3>
                      <p className="text-sm text-gray-500">
                        {assembly.quantity} {assembly.unit} • {assembly.division}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold">${assemblyTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                      <Badge variant="outline" className="mt-1">{assembly.ruleset_used}</Badge>
                    </div>
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <CardContent className="space-y-6">
                    {/* Components */}
                    {assembly.components.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-3 flex items-center gap-2">
                          <Package className="h-4 w-4" />
                          Materials & Components
                        </h4>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Component</TableHead>
                              <TableHead>Quantity</TableHead>
                              <TableHead>Unit Cost</TableHead>
                              <TableHead>Total Cost</TableHead>
                              <TableHead>Source</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {assembly.components.map((comp, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="font-medium">{comp.name}</TableCell>
                                <TableCell>{comp.qty} {comp.unit}</TableCell>
                                <TableCell>
                                  {comp.unit_cost !== null
                                    ? `$${comp.unit_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                                    : "N/A"}
                                </TableCell>
                                <TableCell className="font-medium">
                                  ${comp.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </TableCell>
                                <TableCell>
                                  <Badge variant={comp.cost_source === "ruleset" ? "default" : "secondary"}>
                                    {comp.cost_source}
                                  </Badge>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        <p className="text-sm text-gray-500 mt-2">
                          Materials Total: ${assemblyMaterialCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                      </div>
                    )}

                    {/* Labor */}
                    {assembly.labor.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-3 flex items-center gap-2">
                          <Users className="h-4 w-4" />
                          Labor
                        </h4>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Trade</TableHead>
                              <TableHead>Crew</TableHead>
                              <TableHead>Hours</TableHead>
                              <TableHead>Rate</TableHead>
                              <TableHead>Total Cost</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {assembly.labor.map((lab, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="font-medium">{lab.trade}</TableCell>
                                <TableCell>{lab.crew.join(", ")}</TableCell>
                                <TableCell>{lab.hours.toFixed(1)} hrs</TableCell>
                                <TableCell>
                                  {lab.rate !== null
                                    ? `$${lab.rate.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/hr`
                                    : "N/A"}
                                </TableCell>
                                <TableCell className="font-medium">
                                  ${lab.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        <p className="text-sm text-gray-500 mt-2">
                          Labor Total: ${assemblyLaborCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 
                          ({assembly.labor.reduce((s, l) => s + l.hours, 0).toFixed(1)} total hours)
                        </p>
                      </div>
                    )}

                    {/* Equipment */}
                    {assembly.equipment.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-3 flex items-center gap-2">
                          <Wrench className="h-4 w-4" />
                          Equipment
                        </h4>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Equipment</TableHead>
                              <TableHead>Quantity</TableHead>
                              <TableHead>Unit Cost</TableHead>
                              <TableHead>Total Cost</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {assembly.equipment.map((eq, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="font-medium">{eq.name}</TableCell>
                                <TableCell>{eq.qty} {eq.unit}</TableCell>
                                <TableCell>
                                  {eq.unit_cost !== null
                                    ? `$${eq.unit_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                                    : "N/A"}
                                </TableCell>
                                <TableCell className="font-medium">
                                  ${eq.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        <p className="text-sm text-gray-500 mt-2">
                          Equipment Total: ${assemblyEquipmentCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                      </div>
                    )}

                    {/* Assumptions */}
                    {assembly.assumptions.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-2">Assumptions</h4>
                        <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                          {assembly.assumptions.map((assumption, idx) => (
                            <li key={idx}>{assumption}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Spec References */}
                    {assembly.spec_refs.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-2">Specification References</h4>
                        <div className="flex flex-wrap gap-2">
                          {assembly.spec_refs.map((ref, idx) => (
                            <Badge key={idx} variant="outline">{ref}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </AccordionContent>
              </AccordionItem>
            </Card>
          );
        })}
      </Accordion>
    </div>
  );
}

