"""Institutional room schedule extractor for Stage 2.

Extracts room breakdown (all rooms + areas + totals) from Life Safety Plans
and room schedules for institutional projects.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.institutional_rooms import (
    InstitutionalRoomProgramResult,
    RoomItem,
    RoomProgram,
    RoomProgramTotals,
)
from app.schemas.room_schedule import EvidenceRef, RoomSchedule, RoomScheduleItem
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class InstitutionalRoomExtractor:
    """Extracts room schedules from institutional construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize institutional room extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract_rooms(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> InstitutionalRoomProgramResult:
        """
        Extract room program from institutional document (Phase 4.1).

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            InstitutionalRoomProgramResult with all rooms and totals

        Raises:
            ValueError: If extraction fails or validation fails
        """
        log_ctx = logger.bind(project_id=project_id, stage="institutional_room_extraction")

        log_ctx.info("Starting institutional room extraction (Phase 4.1)")

        # Select pages with room schedule indicators (enhanced selection)
        selected_pages = self._select_room_schedule_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for room extraction")
            return InstitutionalRoomProgramResult(
                rooms=[],
                totals=RoomProgramTotals(),
                missing_fields=["rooms", "totals"],
                confidence=0.0,
            )

        log_ctx.info(f"Pass A: Extracting rooms from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Pass A: Extract rooms from selected pages (targeted read)
        all_rooms: list[RoomItem] = []
        totals_dict: dict[str, Any] = {}
        pages_read = set()

        for page_image in selected_pages[:5]:  # Max 5 pages for Pass A
            try:
                page_result = self._extract_rooms_from_page(page_image, project_id, detail="high")
                pages_read.add(page_image.page_number)
                if page_result.get("rooms"):
                    # Convert dicts to RoomItem objects
                    for room_dict in page_result["rooms"]:
                        try:
                            room = RoomItem.model_validate(room_dict)
                            all_rooms.append(room)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid room item: {e}")
                            continue
                if page_result.get("totals"):
                    totals_dict.update(page_result["totals"])
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Pass B: Gap fill - re-read up to 2 more pages if missing critical data
        missing_critical = []
        if not totals_dict.get("total_existing_gsf") and not totals_dict.get("existing_gsf"):
            missing_critical.append("existing_gsf")
        if not totals_dict.get("total_addition_gsf") and not totals_dict.get("addition_gsf"):
            # Only check if addition is expected (could be None for existing-only projects)
            pass
        if not any(r.floor for r in all_rooms if hasattr(r, 'floor')):
            missing_critical.append("floor_info")
        if not totals_dict.get("total_gsf") and not totals_dict.get("total_new_gsf"):
            missing_critical.append("room_schedule_totals")

        if missing_critical:
            log_ctx.info(f"Pass B: Gap fill needed for: {missing_critical}")
            # Select additional pages (not already read) with strongest indicators
            gap_fill_pages = [
                p for p in selected_pages[5:] if p.page_number not in pages_read
            ][:2]  # Max 2 additional pages
            
            if gap_fill_pages:
                log_ctx.info(f"Pass B: Re-reading {len(gap_fill_pages)} pages: {[p.page_number for p in gap_fill_pages]}")
                for page_image in gap_fill_pages:
                    try:
                        page_result = self._extract_rooms_from_page(page_image, project_id, detail="high")
                        pages_read.add(page_image.page_number)
                        if page_result.get("rooms"):
                            for room_dict in page_result["rooms"]:
                                try:
                                    room = RoomItem.model_validate(room_dict)
                                    # Only add if not duplicate
                                    if not any(
                                        r.room_number == room.room_number and r.room_name == room.room_name
                                        for r in all_rooms
                                    ):
                                        all_rooms.append(room)
                                except ValidationError:
                                    continue
                        if page_result.get("totals"):
                            totals_dict.update(page_result["totals"])
                    except Exception as e:
                        log_ctx.error(f"Pass B: Failed to extract from page {page_image.page_number}: {e}")
                        continue

        # Deduplicate rooms by (room_number, room_name) - keep best evidence
        all_rooms = self._deduplicate_rooms(all_rooms)

        # Build totals object
        totals = RoomProgramTotals(
            existing_gsf=totals_dict.get("total_existing_gsf") or totals_dict.get("existing_gsf"),
            addition_gsf=totals_dict.get("total_addition_gsf") or totals_dict.get("addition_gsf"),
            total_gsf=totals_dict.get("total_new_gsf") or totals_dict.get("total_gsf"),
            existing_gsf_evidence=totals_dict.get("existing_gsf_evidence"),
            addition_gsf_evidence=totals_dict.get("addition_gsf_evidence"),
            total_gsf_evidence=totals_dict.get("total_gsf_evidence"),
        )

        # Validate and potentially trigger recovery
        validation_result = self._validate_room_program(
            all_rooms, totals, analysis, page_index, pdf_images, project_id
        )
        
        # Update all_rooms if recovery added more
        if "updated_rooms" in validation_result:
            all_rooms = validation_result["updated_rooms"]

        # Build missing_fields list
        missing_fields: list[str] = []
        if not all_rooms:
            missing_fields.append("rooms")
        if not totals.existing_gsf and not totals.addition_gsf and not totals.total_gsf:
            missing_fields.append("totals")

        room_program = InstitutionalRoomProgramResult(
            rooms=all_rooms,
            totals=totals,
            missing_fields=missing_fields,
            confidence=validation_result["confidence"],
        )

        log_ctx.info(
            f"Room extraction complete: {len(all_rooms)} rooms, "
            f"totals={totals.existing_gsf or totals.total_gsf}, "
            f"confidence={validation_result['confidence']:.2f}"
        )

        return room_program

    def extract_room_schedule(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> RoomSchedule:
        """
        Extract room schedule in Phase 7.1 format (Phase 7.1).

        This is a wrapper around extract_rooms() that converts to RoomSchedule format.
        Only extracts rooms when explicitly present with evidence.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            RoomSchedule with rooms and evidence
        """
        log_ctx = logger.bind(project_id=project_id, stage="room_schedule_extraction")
        log_ctx.info("Extracting room schedule (Phase 7.1)")

        # Use existing extract_rooms method
        room_program = self.extract_rooms(pdf_images, analysis, page_index, project_id)

        # Convert to RoomSchedule format
        schedule_items: list[RoomScheduleItem] = []
        for room in room_program.rooms:
            # Only include rooms with explicit area and evidence
            if room.area_sf and room.area_sf > 0:
                evidence_ref = EvidenceRef(
                    page_number=room.page_number,
                    sheet_id=room.sheet_id,
                    snippet=room.evidence_snippet,
                )
                schedule_items.append(
                    RoomScheduleItem(
                        room_id=room.room_number,
                        room_name=room.room_name,
                        area_sf=room.area_sf,
                        level=room.floor,
                        usage_type=None,  # Could be inferred from room_name, but keeping deterministic
                        finishes_hint=None,
                        evidence=evidence_ref,
                    )
                )

        # Get total GSF if available
        total_gsf = (
            room_program.totals.total_gsf
            or room_program.totals.existing_gsf
            or room_program.totals.addition_gsf
        )
        total_gsf_evidence = None
        if total_gsf:
            # Create evidence ref from totals (use first room's page if no specific evidence)
            if room_program.totals.total_gsf_evidence:
                # Find a room on a relevant page
                relevant_room = next(
                    (r for r in room_program.rooms if r.page_number > 0), None
                )
                if relevant_room:
                    total_gsf_evidence = EvidenceRef(
                        page_number=relevant_room.page_number,
                        sheet_id=relevant_room.sheet_id,
                        snippet=room_program.totals.total_gsf_evidence,
                    )

        room_schedule = RoomSchedule(
            rooms=schedule_items,
            total_gsf=total_gsf,
            total_gsf_evidence=total_gsf_evidence,
            missing_fields=room_program.missing_fields,
            confidence=room_program.confidence,
        )

        log_ctx.info(
            f"Room schedule extracted: {len(schedule_items)} rooms, "
            f"total_gsf={total_gsf}, confidence={room_program.confidence:.2f}"
        )

        return room_schedule

    def _select_room_schedule_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """
        Select pages containing room schedules (Phase 4.1 - enhanced selection).

        Uses page_index indicators and Stage 1 locators with bias toward:
        - page_types: compliance, plan, schedule, notes
        - indicators: room_schedule, life_safety, occupancy, egress, area
        """
        selected: set[int] = set()

        # Use page_index if available (enhanced selection)
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward compliance, plan, schedule, notes
                relevant_types = ["compliance", "plan", "schedule", "notes"]
                if any(pt in page_item.page_types for pt in relevant_types):
                    selected.add(page_item.page_number - 1)
                
                # Bias toward room schedule indicators
                relevant_indicators = ["room_schedule", "life_safety", "occupancy", "egress", "area"]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    selected.add(page_item.page_number - 1)

        # Use Stage 1 locators
        for locator in analysis.where_quantities_live:
            if locator.location_type in ["room_schedule", "schedule", "life_safety_plan"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Also use select_pages_for_stage2 as base
        from app.services.page_selector import select_pages_for_stage2
        stage2_selection = select_pages_for_stage2(analysis)
        for page_idx in stage2_selection.get("quantity_pages", []):
            selected.add(page_idx)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_rooms_from_page(
        self, page_image: PdfPageImage, project_id: str, detail: str = "high"
    ) -> dict:
        """
        Extract rooms from a single page using OpenAI Vision.

        Returns:
            Dict with 'rooms' (list of RoomItem dicts) and 'totals' (dict with GSF values)
        """
        prompt = self._create_room_extraction_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{page_image.mime_type};base64,{page_image.image_base64}",
                            "detail": detail,  # High detail for room schedule extraction (Phase 7.2)
                        },
                    },
                ],
            }
        ]

        log_ctx = logger.bind(
            project_id=project_id, stage="room_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-rooms-page-{page_image.page_number}",
                stage_name="institutional_room_extraction",
                project_id=project_id,
            )

            # Parse JSON (handle markdown code blocks)
            content = response_text.strip()
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            elif content.startswith("```"):
                content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

            parsed = json.loads(content)

            # Convert room dicts to RoomItem objects (validate)
            rooms: list[dict] = []
            for room_dict in parsed.get("rooms", []):
                try:
                    room_dict["page_number"] = page_image.page_number
                    # Ensure required fields
                    if "room_name" not in room_dict and "name" in room_dict:
                        room_dict["room_name"] = room_dict.pop("name")
                    if "room_number" not in room_dict and "room_id" in room_dict:
                        room_dict["room_number"] = room_dict.pop("room_id")
                    # Validate structure
                    RoomItem.model_validate(room_dict)  # Validate but don't convert yet
                    rooms.append(room_dict)
                except ValidationError as e:
                    log_ctx.warning(f"Invalid room item: {e}")
                    continue

            # Convert totals dict
            totals_dict = parsed.get("totals", {})
            # Map old field names to new ones
            if "total_existing_gsf" in totals_dict:
                totals_dict["existing_gsf"] = totals_dict.pop("total_existing_gsf")
            if "total_addition_gsf" in totals_dict:
                totals_dict["addition_gsf"] = totals_dict.pop("total_addition_gsf")
            if "total_new_gsf" in totals_dict:
                totals_dict["total_gsf"] = totals_dict.pop("total_new_gsf")

            return {
                "rooms": rooms,
                "totals": totals_dict,
            }

        except Exception as e:
            log_ctx.error(f"Failed to extract rooms from page {page_image.page_number}: {e}")
            raise

    def _create_room_extraction_prompt(self) -> str:
        """Create prompt for room schedule extraction (Phase 4.1)."""
        return """You are extracting a room schedule from a construction document (Life Safety Plan / Code plan).

Extract ALL rooms listed on this page. For each room, include:
- Room number (if visible, e.g., "101", "A-101")
- Room name (required)
- Area in square feet (SF) if visible
- Floor level (if visible, e.g., "Ground", "First", "Basement")
- Sheet ID if visible (e.g., "A-3", "LS-1")
- Evidence snippet: exact text showing this room (required)

Also extract totals if visible:
- Existing GSF (Gross Square Feet)
- Addition GSF
- Total GSF
- Evidence snippets for each total

IMPORTANT: Do not fabricate rooms or areas. If information is unclear, omit it. Every room must have page_number and evidence_snippet.

Return ONLY valid JSON matching this schema:

{
  "rooms": [
    {
      "room_number": "101" or null,
      "room_name": "Gymnasium",
      "area_sf": 2500.0 or null,
      "floor": "Ground" or null,
      "sheet_id": "A-3" or null,
      "evidence_snippet": "Exact text showing this room"
    }
  ],
  "totals": {
    "existing_gsf": 15000.0 or null,
    "addition_gsf": 5000.0 or null,
    "total_gsf": null,
    "existing_gsf_evidence": "Evidence text" or null,
    "addition_gsf_evidence": "Evidence text" or null,
    "total_gsf_evidence": null
  }
}

Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _validate_room_program(
        self,
        rooms: list[RoomItem],
        totals: RoomProgramTotals,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
        project_id: str,
    ) -> dict[str, Any]:
        """
        Validate room program and trigger recovery if needed (Phase 4.1).

        Validation gates:
        - room_count_min (default 15)
        - Area sum tolerance (±5% configurable)
        - Must include at least one "top room" by area

        Returns:
            Dict with validation results and potentially updated rooms/totals
        """
        log_ctx = logger.bind(project_id=project_id, stage="room_program_validation")
        
        room_count_min = getattr(self.settings, "institutional_room_count_min", 15)
        tolerance_pct = getattr(self.settings, "institutional_room_area_tolerance_pct", 5.0)
        
        validation_passed = True
        issues: list[str] = []
        confidence = 1.0

        # Gate 1: Minimum room count
        if len(rooms) < room_count_min:
            validation_passed = False
            issues.append(f"Room count {len(rooms)} is below minimum {room_count_min}")
            confidence = max(0.0, len(rooms) / room_count_min * 0.5)  # Scale confidence down
        
        # Gate 2: Area sum vs totals tolerance
        if totals.existing_gsf or totals.addition_gsf or totals.total_gsf:
            stated_total = totals.existing_gsf or totals.addition_gsf or totals.total_gsf
            extracted_sum = sum(room.area_sf or 0.0 for room in rooms if room.area_sf)
            
            if stated_total and extracted_sum > 0:
                diff_pct = abs(extracted_sum - stated_total) / stated_total * 100
                if diff_pct > tolerance_pct:
                    validation_passed = False
                    issues.append(
                        f"Extracted rooms sum ({extracted_sum:.0f} SF) differs from stated total "
                        f"({stated_total:.0f} SF) by {diff_pct:.1f}% (threshold: ±{tolerance_pct}%)"
                    )
                    confidence = max(0.3, confidence * (1.0 - (diff_pct / 100) * 0.5))
        
        # Gate 3: Must have at least one "top room" by area (largest room)
        if rooms:
            rooms_with_area = [r for r in rooms if r.area_sf and r.area_sf > 0]
            if rooms_with_area:
                max_area = max(r.area_sf for r in rooms_with_area)
                # Check if max area is reasonable (at least 100 SF for institutional)
                if max_area < 100:
                    validation_passed = False
                    issues.append(f"Largest room area ({max_area:.0f} SF) seems too small - extraction likely incomplete")
                    confidence *= 0.7
            else:
                validation_passed = False
                issues.append("No rooms with area found - cannot validate completeness")
                confidence *= 0.5

        # Trigger recovery if validation failed
        if not validation_passed:
            log_ctx.warning(f"Room program validation failed: {', '.join(issues)}")
            log_ctx.info("Triggering targeted recovery re-read")
            
            recovery_rooms = self._recover_rooms(
                rooms, analysis, page_index, pdf_images, project_id
            )
            
            # Merge recovery results (additive, deduplicate)
            if recovery_rooms:
                all_rooms_dict: dict[tuple[str | None, str], RoomItem] = {}
                
                # Index existing rooms by (room_number, room_name)
                for room in rooms:
                    key = (room.room_number, room.room_name)
                    all_rooms_dict[key] = room
                
                # Add recovery rooms (prefer better evidence)
                for room in recovery_rooms:
                    key = (room.room_number, room.room_name)
                    if key not in all_rooms_dict:
                        all_rooms_dict[key] = room
                    else:
                        # Keep the one with better evidence (longer snippet or higher area)
                        existing = all_rooms_dict[key]
                        if len(room.evidence_snippet) > len(existing.evidence_snippet) or (
                            room.area_sf and existing.area_sf and room.area_sf > existing.area_sf
                        ):
                            all_rooms_dict[key] = room
                
                rooms = list(all_rooms_dict.values())
                
                # Re-validate after recovery
                if len(rooms) >= room_count_min:
                    validation_passed = True
                    issues = []
                    confidence = min(1.0, confidence + 0.2)  # Boost confidence after recovery
                    log_ctx.info(f"Recovery successful: now have {len(rooms)} rooms")
                
                return {
                    "validation_passed": validation_passed,
                    "issues": issues,
                    "confidence": confidence,
                    "updated_rooms": rooms,  # Return updated rooms
                }
        
        return {
            "validation_passed": validation_passed,
            "issues": issues,
            "confidence": confidence,
        }
    
    def _recover_rooms(
        self,
        existing_rooms: list[RoomItem],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
        project_id: str,
    ) -> list[RoomItem]:
        """
        Perform targeted recovery re-read for missing rooms (Phase 4.1).

        Re-reads up to 4 additional pages chosen by page_index with strongest
        room_schedule/life_safety indicators.
        """
        log_ctx = logger.bind(project_id=project_id, stage="room_recovery")
        
        # Select recovery pages (up to 4)
        recovery_pages: list[PdfPageImage] = []
        already_read_pages = {room.page_number for room in existing_rooms}
        
        if page_index and hasattr(page_index, "pages"):
            # Score pages by room schedule indicators
            scored_pages: list[tuple[int, float]] = []
            
            for page_item in page_index.pages:
                page_num = page_item.page_number
                if page_num in already_read_pages:
                    continue  # Skip already read pages
                
                score = 0.0
                # Boost for strong indicators
                if "room_schedule" in page_item.indicators:
                    score += 10.0
                if "life_safety" in page_item.indicators:
                    score += 8.0
                if "occupancy" in page_item.indicators or "egress" in page_item.indicators:
                    score += 5.0
                if "area" in page_item.indicators:
                    score += 3.0
                
                # Boost for relevant page types
                if "schedule" in page_item.page_types:
                    score += 8.0
                if "plan" in page_item.page_types:
                    score += 5.0
                if "compliance" in page_item.page_types:
                    score += 5.0
                
                score *= page_item.confidence
                
                page_idx = page_num - 1
                if 0 <= page_idx < len(pdf_images):
                    scored_pages.append((page_idx, score))
            
            # Sort by score and take top 4
            scored_pages.sort(key=lambda x: x[1], reverse=True)
            recovery_indices = [idx for idx, _ in scored_pages[:4]]
            
            recovery_pages = [
                pdf_images[i] for i in recovery_indices if 0 <= i < len(pdf_images)
            ]
        
        if not recovery_pages:
            log_ctx.warning("No additional pages available for recovery")
            return []
        
        log_ctx.info(f"Recovery: re-reading {len(recovery_pages)} pages: {[p.page_number for p in recovery_pages]}")
        
        # Extract from recovery pages
        recovery_rooms: list[RoomItem] = []
        for page_image in recovery_pages:
            try:
                page_result = self._extract_rooms_from_page(page_image, project_id)
                if page_result.get("rooms"):
                    for room_dict in page_result["rooms"]:
                        try:
                            room_dict["page_number"] = page_image.page_number
                            # Ensure required fields
                            if "room_name" not in room_dict and "name" in room_dict:
                                room_dict["room_name"] = room_dict.pop("name")
                            if "room_number" not in room_dict and "room_id" in room_dict:
                                room_dict["room_number"] = room_dict.pop("room_id")
                            room = RoomItem.model_validate(room_dict)
                            recovery_rooms.append(room)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid recovery room item: {e}")
                            continue
            except Exception as e:
                log_ctx.error(f"Failed recovery extraction from page {page_image.page_number}: {e}")
                continue
        
        return recovery_rooms
    
    def _deduplicate_rooms(self, rooms: list[RoomItem]) -> list[RoomItem]:
        """
        Deduplicate rooms by (room_number, room_name), keeping best evidence.
        """
        rooms_dict: dict[tuple[str | None, str], RoomItem] = {}
        
        for room in rooms:
            key = (room.room_number, room.room_name)
            if key not in rooms_dict:
                rooms_dict[key] = room
            else:
                # Keep the one with better evidence (longer snippet or higher area)
                existing = rooms_dict[key]
                if len(room.evidence_snippet) > len(existing.evidence_snippet) or (
                    room.area_sf and existing.area_sf and room.area_sf > existing.area_sf
                ):
                    rooms_dict[key] = room
        
        return list(rooms_dict.values())

