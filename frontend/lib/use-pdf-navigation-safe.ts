/** Safe hook for PDF navigation (Phase 8.6C).
 * 
 * Returns null if PDF navigation context is not available.
 */

"use client";

import { useContext } from "react";
import { PdfNavigationContext } from "./pdf-navigation-context";

export function usePdfNavigationSafe() {
  const context = useContext(PdfNavigationContext);
  return context || null;
}






