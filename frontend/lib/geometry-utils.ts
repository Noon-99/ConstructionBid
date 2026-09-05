/**
 * Geometry utility functions for 3D model calculations.
 */

export interface BoundingBox {
  min: { x: number; y: number; z: number };
  max: { x: number; y: number; z: number };
}

/**
 * Calculate width, depth, and height from a bounding box.
 */
export function getBoundingBoxDimensions(bbox: BoundingBox): {
  width: number;
  depth: number;
  height: number;
} {
  return {
    width: bbox.max.x - bbox.min.x,
    depth: bbox.max.y - bbox.min.y,
    height: bbox.max.z - bbox.min.z,
  };
}

/**
 * Calculate footprint area (width × depth).
 */
export function getFootprintArea(bbox: BoundingBox): number {
  const dims = getBoundingBoxDimensions(bbox);
  return dims.width * dims.depth;
}

/**
 * Calculate volume (width × depth × height).
 */
export function getVolume(bbox: BoundingBox): number {
  const dims = getBoundingBoxDimensions(bbox);
  return dims.width * dims.depth * dims.height;
}

/**
 * Get center point of bounding box.
 */
export function getBoundingBoxCenter(bbox: BoundingBox): {
  x: number;
  y: number;
  z: number;
} {
  return {
    x: (bbox.min.x + bbox.max.x) / 2,
    y: (bbox.min.y + bbox.max.y) / 2,
    z: (bbox.min.z + bbox.max.z) / 2,
  };
}

/**
 * Calculate scene bounding box from all buildings and zones.
 */
export function getSceneBoundingBox(
  buildings: Array<{ bounding_box: BoundingBox }>,
  zones: Array<{ bounding_box: BoundingBox | null }>
): BoundingBox | null {
  const allBoxes: BoundingBox[] = [];

  buildings.forEach((b) => allBoxes.push(b.bounding_box));
  zones.forEach((z) => {
    if (z.bounding_box) allBoxes.push(z.bounding_box);
  });

  if (allBoxes.length === 0) return null;

  let minX = Infinity,
    minY = Infinity,
    minZ = Infinity;
  let maxX = -Infinity,
    maxY = -Infinity,
    maxZ = -Infinity;

  allBoxes.forEach((bbox) => {
    minX = Math.min(minX, bbox.min.x);
    minY = Math.min(minY, bbox.min.y);
    minZ = Math.min(minZ, bbox.min.z);
    maxX = Math.max(maxX, bbox.max.x);
    maxY = Math.max(maxY, bbox.max.y);
    maxZ = Math.max(maxZ, bbox.max.z);
  });

  return {
    min: { x: minX, y: minY, z: minZ },
    max: { x: maxX, y: maxY, z: maxZ },
  };
}






