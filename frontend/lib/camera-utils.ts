/**
 * Camera utilities for 3D viewer fly-to navigation (Phase 8.5).
 */

import * as THREE from "three";

export interface BoundingBox {
  min: { x: number; y: number; z: number };
  max: { x: number; y: number; z: number };
}

export interface FocusTarget {
  center: THREE.Vector3;
  radius: number;
}

/**
 * Compute focus target from bounding box.
 */
export function computeFocusFromBBox(bbox: BoundingBox): FocusTarget {
  const center = new THREE.Vector3(
    (bbox.min.x + bbox.max.x) / 2,
    (bbox.min.z + bbox.max.z) / 2, // Y-up to Z-up conversion
    (bbox.min.y + bbox.max.y) / 2
  );

  const size = new THREE.Vector3(
    bbox.max.x - bbox.min.x,
    bbox.max.z - bbox.min.z, // Y-up to Z-up conversion
    bbox.max.y - bbox.min.y
  );

  const radius = Math.max(size.x, size.y, size.z) * 1.5; // 1.5x padding

  return { center, radius };
}

/**
 * Fly camera to target with smooth animation.
 */
export function flyTo(
  camera: THREE.PerspectiveCamera,
  controls: any, // OrbitControls
  target: FocusTarget,
  durationMs: number = 650,
  onComplete?: () => void
): void {
  const startPosition = camera.position.clone();
  const startTarget = controls.target.clone();
  const endPosition = new THREE.Vector3(
    target.center.x + target.radius * 0.7,
    target.center.y + target.radius * 0.7,
    target.center.z + target.radius * 0.7
  );
  const endTarget = target.center.clone();

  const startTime = performance.now();

  const animate = () => {
    const elapsed = performance.now() - startTime;
    const progress = Math.min(elapsed / durationMs, 1);

    // Easing function (ease-in-out cubic)
    const eased = progress < 0.5
      ? 4 * progress * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 3) / 2;

    // Interpolate position
    camera.position.lerpVectors(startPosition, endPosition, eased);
    controls.target.lerpVectors(startTarget, endTarget, eased);
    controls.update();

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      if (onComplete) {
        onComplete();
      }
    }
  };

  animate();
}






