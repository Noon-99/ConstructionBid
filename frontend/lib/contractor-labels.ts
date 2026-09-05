/**
 * Contractor-friendly label mappings (Task 7).
 * Maps internal IDs to contractor-style language.
 */

export const contractorLabels: Record<string, string> = {
  // Zone/package name mappings
  parapet_repair: "Parapet Reconstruction",
  parapet_perimeter: "Parapet Perimeter",
  lintel_replacement: "Window Lintel Replacement",
  lintel_band: "Lintel Band",
  brick_repointing: "Repointing",
  repointing: "Repointing",
  crack_repair: "Crack Repairs",
  crack_repair_zone: "Crack Repair Zone",
  flashing_installation: "Flashing Installation",
  flashing_repair: "Flashing Repair",
  masonry_repair: "Masonry Repair",
  masonry_rebuild: "Brick Rebuild",
  foundation_repair: "Foundation Repair",
  foundation_band: "Foundation Band",
  water_table_band: "Water Table",
  roof_edge: "Roof Edge",
  roof_coping: "Roof Coping",
  
  // Package title mappings (common patterns)
  "parapet_reconstruction": "Parapet Reconstruction",
  "lintel_replacement_package": "Window Lintel Replacement",
  "brick_repointing_package": "Repointing",
  "crack_repair_package": "Crack Repairs",
  "flashing_package": "Flashing Installation",
  "masonry_package": "Masonry Repair",
  
  // Division mappings
  "04 Masonry": "Masonry",
  "05 Metals": "Metals",
  "06 Wood": "Wood",
  "07 Thermal": "Waterproofing/Thermal",
  "08 Openings": "Openings",
  "09 Finishes": "Finishes",
  "10 Specialties": "Specialties",
};

/**
 * Get contractor-friendly label for an internal ID.
 * Falls back to the ID if no mapping exists.
 */
export function getContractorLabel(id: string): string {
  // Try exact match first
  if (contractorLabels[id]) {
    return contractorLabels[id];
  }
  
  // Try case-insensitive match
  const lowerId = id.toLowerCase();
  const match = Object.keys(contractorLabels).find(
    (key) => key.toLowerCase() === lowerId
  );
  if (match) {
    return contractorLabels[match];
  }
  
  // Try partial match (e.g., "parapet_repair_zone" matches "parapet_repair")
  const partialMatch = Object.keys(contractorLabels).find((key) =>
    lowerId.includes(key.toLowerCase()) || key.toLowerCase().includes(lowerId)
  );
  if (partialMatch) {
    return contractorLabels[partialMatch];
  }
  
  // Fallback: format ID nicely (replace underscores, capitalize words)
  return id
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Format a package title using contractor labels.
 */
export function formatPackageTitle(title: string): string {
  return getContractorLabel(title);
}





