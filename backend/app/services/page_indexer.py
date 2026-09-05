"""Page indexer service for Stage 0.5.

Scans all PDF pages and produces a structured catalog describing what each page contains.
This eliminates guessing in Stage 1 page selection.
"""

import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import json
from threading import Semaphore
from typing import Any, Callable

from loguru import logger

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.page_index import PageIndex, PageIndexItem
from app.services.openai_client import OpenAIClient


class PageIndexer:
    """Indexes PDF pages to identify page types and key indicators."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize page indexer."""
        self.settings = settings
        self.openai_client = openai_client

    def _get_cache_dir(self, project_id: str) -> Path:
        """
        Get the cache directory for per-page indexing results.

        Args:
            project_id: Project ID

        Returns:
            Path to cache directory
        """
        cache_dir = Path("out") / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _get_cached_page_path(self, project_id: str, page_number: int) -> Path:
        """
        Get the cache file path for a specific page.

        Args:
            project_id: Project ID
            page_number: 1-indexed page number

        Returns:
            Path to cache file
        """
        cache_dir = self._get_cache_dir(project_id)
        return cache_dir / f"page_{page_number}.json"

    def _load_cached_page(self, project_id: str, page_number: int) -> PageIndexItem | None:
        """
        Load a cached page index result if it exists.

        Args:
            project_id: Project ID
            page_number: 1-indexed page number

        Returns:
            PageIndexItem if cached, None otherwise
        """
        cache_path = self._get_cached_page_path(project_id, page_number)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            cached_item = PageIndexItem.model_validate(data)
            return self._augment_window_signals(cached_item)
        except Exception as e:
            logger.bind(project_id=project_id, page=page_number).warning(
                f"Failed to load cached page {page_number}: {e}"
            )
            return None

    def _save_cached_page(
        self, project_id: str, page_item: PageIndexItem
    ) -> None:
        """
        Save a page index result to cache.

        Args:
            project_id: Project ID
            page_item: PageIndexItem to cache
        """
        cache_path = self._get_cached_page_path(project_id, page_item.page_number)
        try:
            with open(cache_path, "w") as f:
                f.write(page_item.model_dump_json(indent=2))
        except Exception as e:
            logger.bind(project_id=project_id, page=page_item.page_number).warning(
                f"Failed to save cached page {page_item.page_number}: {e}"
            )

    def _update_progress(
        self,
        project_id: str,
        total_pages: int,
        completed_pages: int,
        cached_pages: int,
        failed_pages: int,
    ) -> None:
        """
        Update progress tracking file.

        Args:
            project_id: Project ID
            total_pages: Total number of pages
            completed_pages: Number of completed pages
            cached_pages: Number of cached pages
            failed_pages: Number of failed pages
        """
        output_dir = Path("out") / project_id
        progress_file = output_dir / "page_index_progress.json"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            progress_data = {
                "total_pages": total_pages,
                "completed_pages": completed_pages,
                "cached_pages": cached_pages,
                "failed_pages": failed_pages,
                "updated_at": datetime.now().isoformat(),
            }
            with open(progress_file, "w") as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            logger.bind(project_id=project_id).warning(f"Failed to update progress: {e}")

    async def _index_single_page_with_retry(
        self,
        page_image: PdfPageImage,
        project_id: str,
        semaphore: asyncio.Semaphore,
        max_retries: int,
    ) -> PageIndexItem:
        """
        Index a single page with retry logic and concurrency control.

        Args:
            page_image: Page image to index
            project_id: Project ID for logging
            semaphore: Semaphore for concurrency control
            max_retries: Maximum number of retry attempts

        Returns:
            PageIndexItem with classification
        """
        log_ctx = logger.bind(
            project_id=project_id, stage="page_indexing", page=page_image.page_number
        )

        async with semaphore:
            # Check cache again (in case it was cached by another concurrent task)
            cached_item = self._load_cached_page(project_id, page_image.page_number)
            if cached_item:
                log_ctx.debug(f"Page {page_image.page_number} was cached concurrently")
                return cached_item

            # Retry logic with exponential backoff
            last_exception = None
            for attempt in range(max_retries):
                try:
                    # Run the sync indexing function in executor
                    loop = asyncio.get_event_loop()
                    page_item = await loop.run_in_executor(
                        None,
                        self._index_single_page,
                        page_image,
                        project_id,
                    )

                    # Save to cache
                    self._save_cached_page(project_id, page_item)
                    return page_item

                except Exception as e:
                    last_exception = e
                    error_str = str(e).lower()

                    # Check if error is retryable (429, 5xx, timeout)
                    is_retryable = (
                        "429" in error_str
                        or "rate limit" in error_str
                        or "500" in error_str
                        or "502" in error_str
                        or "503" in error_str
                        or "timeout" in error_str
                        or "timed out" in error_str
                    )

                    if not is_retryable or attempt == max_retries - 1:
                        # Non-retryable error or max retries reached
                        log_ctx.error(
                            f"Failed to index page {page_image.page_number} "
                            f"(attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        break

                    # Exponential backoff with jitter
                    base_delay = 2 ** attempt  # 1, 2, 4, 8, 16, 32 seconds
                    jitter = random.uniform(0, 1)  # 0-1 second random jitter
                    delay = base_delay + jitter

                    log_ctx.warning(
                        f"Retryable error indexing page {page_image.page_number} "
                        f"(attempt {attempt + 1}/{max_retries}), retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)

            # All retries failed, return fallback
            log_ctx.error(
                f"Failed to index page {page_image.page_number} after {max_retries} attempts"
            )
            fallback_item = PageIndexItem(
                page_number=page_image.page_number,
                page_types=["unknown"],
                indicators=[],
                confidence=0.0,
            )
            # Cache the fallback to avoid repeated failures
            self._save_cached_page(project_id, fallback_item)
            return fallback_item

    async def _process_batch(
        self,
        batch: list[PdfPageImage],
        project_id: str,
        semaphore: asyncio.Semaphore,
        max_retries: int,
    ) -> list[PageIndexItem]:
        """
        Process a batch of pages concurrently.

        Args:
            batch: List of page images to process
            project_id: Project ID for logging
            semaphore: Semaphore for concurrency control
            max_retries: Maximum number of retry attempts

        Returns:
            List of PageIndexItem results (may be out of order)
        """
        tasks = [
            self._index_single_page_with_retry(page_image, project_id, semaphore, max_retries)
            for page_image in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions (should not happen due to retry logic, but be safe)
        page_items: list[PageIndexItem] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.bind(project_id=project_id).error(
                    f"Unexpected error indexing page {batch[i].page_number}: {result}"
                )
                page_items.append(
                    PageIndexItem(
                        page_number=batch[i].page_number,
                        page_types=["unknown"],
                        indicators=[],
                        confidence=0.0,
                    )
                )
            else:
                page_items.append(result)

        return page_items

    def index_pages(
        self,
        project_id: str,
        page_images: list[PdfPageImage],
        force_reindex: bool = False,
        dry_run: bool = False,
    ) -> PageIndex | dict[str, Any]:
        """
        Index all pages to identify types and indicators.

        Supports per-page caching and resumability for large PDFs.
        If a page is already cached, it will be loaded from cache unless force_reindex=True.

        Args:
            project_id: Project ID for logging
            page_images: List of page images from Stage 0
            force_reindex: If True, ignore cache and re-index all pages

        Returns:
            PageIndex with classification for each page
        """
        log_ctx = logger.bind(project_id=project_id, stage="page_indexing")
        started_at = datetime.now()

        total_pages = len(page_images)
        max_pages = self.settings.max_page_index_pages
        smart_mode_threshold = self.settings.page_index_smart_mode_threshold
        batch_size = self.settings.page_index_batch_size
        concurrency = self.settings.page_index_concurrency
        max_retries = self.settings.page_index_max_retries

        # Batch 4: Hard cap validation
        if total_pages > max_pages:
            error_msg = (
                f"Page count ({total_pages}) exceeds maximum allowed ({max_pages}). "
                f"To override, increase MAX_PAGE_INDEX_PAGES config. "
                f"Current limit is set for cost control."
            )
            log_ctx.error(error_msg)
            raise ValueError(error_msg)

        # Batch 4: Smart mode threshold check (already using smart mode with batching + concurrency)
        using_smart_mode = total_pages > smart_mode_threshold
        if using_smart_mode:
            log_ctx.info(
                f"Large PDF detected ({total_pages} pages > {smart_mode_threshold} threshold), "
                f"using smart index mode (caching + concurrency)"
            )

        log_ctx.info(
            f"Starting page indexing for {total_pages} pages "
            f"(force_reindex={force_reindex}, dry_run={dry_run}, "
            f"batch_size={batch_size}, concurrency={concurrency})"
        )

        # Ensure cache directory exists
        self._get_cache_dir(project_id)

        # TASK 2: Fast mode for large PDFs - determine which pages to index
        using_fast_mode = total_pages >= self.settings.page_index_fast_mode_threshold
        fast_mode_metadata = {}
        
        if using_fast_mode:
            log_ctx.info(
                f"Fast indexing mode enabled ({total_pages} pages >= {self.settings.page_index_fast_mode_threshold})"
            )
            # Select candidate pages for fast mode sampling
            candidate_page_numbers = self._select_fast_mode_candidate_pages(
                total_pages,
                self.settings.page_index_fast_max_pages,
                self.settings.page_index_stride,
            )
            log_ctx.info(
                f"Fast mode: selected {len(candidate_page_numbers)} candidate pages for initial indexing"
            )
            fast_mode_metadata = {
                "fast_mode": True,
                "candidate_pages_count": len(candidate_page_numbers),
                "total_pages": total_pages,
            }
        else:
            # Normal mode: index all pages
            candidate_page_numbers = None
            fast_mode_metadata = {"fast_mode": False}

        # Load cached pages first
        indexed_pages: list[PageIndexItem] = []
        cached_count = 0
        pages_to_index: list[PdfPageImage] = []

        for page_image in page_images:
            # Skip pages not in candidate set for fast mode
            if using_fast_mode and candidate_page_numbers:
                if page_image.page_number not in candidate_page_numbers:
                    # Create a placeholder for non-indexed pages (will be expanded later if needed)
                    continue
            
            if not force_reindex:
                cached_item = self._load_cached_page(project_id, page_image.page_number)
                if cached_item:
                    indexed_pages.append(cached_item)
                    cached_count += 1
                    continue
            pages_to_index.append(page_image)

        # Batch 4: Dry run mode - return workload prediction without executing
        if dry_run:
            # For fast mode, predict based on candidate pages + potential expansion
            if using_fast_mode and candidate_page_numbers:
                estimated_candidate_count = len([p for p in candidate_page_numbers if p not in [item.page_number for item in indexed_pages]])
                # Estimate expansion (assume ~30% of candidates are hot, expand around them)
                estimated_expansion = min(
                    self.settings.page_index_expand_radius * 2 * len(candidate_page_numbers) // 3,
                    self.settings.page_index_fast_max_pages - len(candidate_page_numbers)
                )
                estimated_pages = estimated_candidate_count + estimated_expansion
            else:
                estimated_pages = len(pages_to_index)
            
            predicted_batches = (estimated_pages + batch_size - 1) // batch_size if estimated_pages > 0 else 0
            return {
                "dry_run": True,
                "project_id": project_id,
                "total_pages": total_pages,
                "cached_pages": cached_count,
                "pages_to_index": estimated_pages,
                "predicted_batches": predicted_batches,
                "estimated_api_calls": estimated_pages,  # Assuming no retries for estimate
                "using_smart_mode": using_smart_mode,
                "using_fast_mode": using_fast_mode,
                "workload_summary": {
                    "total_pages": total_pages,
                    "cached_pages": cached_count,
                    "pages_to_index": estimated_pages,
                    "cache_hit_rate": round((cached_count / total_pages) * 100, 2) if total_pages > 0 else 0.0,
                    "predicted_batches": predicted_batches,
                    "concurrency": concurrency,
                    "batch_size": batch_size,
                    "fast_mode": using_fast_mode,
                },
            }

        newly_indexed_count = 0
        failed_count = 0
        retries_count = 0  # Batch 4: Track retries (approximate - will track in async function)
        if pages_to_index:
            log_ctx.info(
                f"Indexing {len(pages_to_index)} pages in batches of {batch_size} "
                f"(concurrency={concurrency})"
            )

            # Split into batches
            batches = [
                pages_to_index[i : i + batch_size]
                for i in range(0, len(pages_to_index), batch_size)
            ]

            # Process batches
            for batch_num, batch in enumerate(batches, 1):
                log_ctx.info(
                    f"Processing batch {batch_num}/{len(batches)} "
                    f"({len(batch)} pages)"
                )

                # Create async wrapper that creates semaphore in the async context
                async def process_batch_with_semaphore():
                    semaphore = asyncio.Semaphore(concurrency)
                    return await self._process_batch(batch, project_id, semaphore, max_retries)

                # Run async batch processing
                # Handle event loop safely (works in sync and async contexts)
                try:
                    loop = asyncio.get_running_loop()
                    # If we're already in an async context, create a new event loop in a thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            process_batch_with_semaphore()
                        )
                        batch_results = future.result()
                except RuntimeError:
                    # No running loop, safe to use asyncio.run
                    batch_results = asyncio.run(process_batch_with_semaphore())

                # Add results (may be out of order, will sort later)
                for page_item in batch_results:
                    indexed_pages.append(page_item)
                    if page_item.confidence == 0.0 and page_item.page_types == ["unknown"]:
                        failed_count += 1
                    else:
                        newly_indexed_count += 1

                # Update progress
                completed = len(indexed_pages)
                self._update_progress(
                    project_id, total_pages, completed, cached_count, failed_count
                )

                log_ctx.info(
                    f"Indexed {completed}/{total_pages} pages "
                    f"(cached {cached_count}, newly indexed {newly_indexed_count}, failed {failed_count})"
                )

        # TASK 2: Fast mode expansion - identify hot pages and expand around them
        if using_fast_mode and indexed_pages:
            hot_pages = self._identify_hot_pages(indexed_pages)
            if hot_pages:
                log_ctx.info(f"Fast mode: found {len(hot_pages)} hot pages, expanding by ±{self.settings.page_index_expand_radius}")
                expansion_pages = self._expand_around_hot_pages(
                    hot_pages,
                    total_pages,
                    self.settings.page_index_expand_radius,
                    set(p.page_number for p in indexed_pages),  # Already indexed
                    self.settings.page_index_fast_max_pages,
                )
                
                if expansion_pages:
                    log_ctx.info(f"Fast mode: expanding to index {len(expansion_pages)} additional pages around hot pages")
                    # Get page images for expansion pages
                    expansion_images = [
                        img for img in page_images
                        if img.page_number in expansion_pages
                        and (force_reindex or not self._load_cached_page(project_id, img.page_number))
                    ]
                    
                    if expansion_images:
                        # Index expansion pages using same ThreadPoolExecutor pattern
                        expansion_semaphore = Semaphore(concurrency)
                        
                        def index_expansion_page(page_image: PdfPageImage) -> PageIndexItem:
                            expansion_semaphore.acquire()
                            try:
                                if not force_reindex:
                                    cached_item = self._load_cached_page(project_id, page_image.page_number)
                                    if cached_item:
                                        return cached_item
                                
                                # Retry logic (simplified for expansion - use same pattern as main indexing)
                                for attempt in range(max_retries):
                                    try:
                                        page_item = self._index_single_page(page_image, project_id)
                                        self._save_cached_page(project_id, page_item)
                                        return page_item
                                    except Exception as e:
                                        if attempt == max_retries - 1:
                                            return PageIndexItem(
                                                page_number=page_image.page_number,
                                                page_types=["unknown"],
                                                indicators=[],
                                                confidence=0.0,
                                            )
                                        time.sleep(2 ** attempt + random.uniform(0, 1))
                                return PageIndexItem(
                                    page_number=page_image.page_number,
                                    page_types=["unknown"],
                                    indicators=[],
                                    confidence=0.0,
                                )
                            finally:
                                expansion_semaphore.release()
                        
                        expansion_results_dict: dict[int, PageIndexItem] = {}
                        with ThreadPoolExecutor(max_workers=concurrency) as executor:
                            future_to_page = {
                                executor.submit(index_expansion_page, img): img.page_number
                                for img in expansion_images
                            }
                            for future in as_completed(future_to_page):
                                page_number = future_to_page[future]
                                try:
                                    expansion_results_dict[page_number] = future.result()
                                except Exception as e:
                                    log_ctx.error(f"Error indexing expansion page {page_number}: {e}")
                                    expansion_results_dict[page_number] = PageIndexItem(
                                        page_number=page_number,
                                        page_types=["unknown"],
                                        indicators=[],
                                        confidence=0.0,
                                    )
                        
                        # Add expansion results in order
                        for page_number in sorted(expansion_results_dict.keys()):
                            page_item = expansion_results_dict[page_number]
                            indexed_pages.append(page_item)
                            if page_item.confidence == 0.0 and page_item.page_types == ["unknown"]:
                                failed_count += 1
                            else:
                                newly_indexed_count += 1
                        
                        fast_mode_metadata["expansion_pages_count"] = len(expansion_images)
                        fast_mode_metadata["hot_pages"] = sorted(hot_pages)

        # Sort by page number to ensure deterministic ordering (1..N)
        indexed_pages.sort(key=lambda p: p.page_number)

        finished_at = datetime.now()

        # Batch 4: Calculate metrics
        indexed_pages_count = newly_indexed_count
        cache_hit_rate = round((cached_count / total_pages) * 100, 2) if total_pages > 0 else 0.0
        
        metrics = {
            "indexed_pages_count": indexed_pages_count,
            "cache_hit_rate": cache_hit_rate,
            "retries_count": retries_count,  # Approximate - detailed tracking would require async context
            "failed_pages_count": failed_count,
            "total_api_calls": indexed_pages_count,  # Approximate (doesn't account for retries in detail)
        }

        # Create PageIndex with metadata (include fast mode metadata in metrics)
        if fast_mode_metadata:
            metrics["fast_mode_metadata"] = fast_mode_metadata
        
        page_index = PageIndex(
            project_id=project_id,
            pages=indexed_pages,
            total_pages=total_pages,
            indexed_pages=len(indexed_pages),
            cached_pages=cached_count,
            started_at=started_at,
            finished_at=finished_at,
            metrics=metrics,
        )

        log_ctx.info(
            f"Page indexing complete: {len(indexed_pages)} pages indexed "
            f"({cached_count} from cache, {newly_indexed_count} newly indexed), "
            f"{sum(1 for p in indexed_pages if p.confidence > 0.7)} high-confidence pages"
        )

        return page_index

    def _index_single_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> PageIndexItem:
        """
        Index a single page using OpenAI Vision.

        Args:
            page_image: Page image to index
            project_id: Project ID for logging

        Returns:
            PageIndexItem with classification
        """
        prompt = self._create_indexing_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{page_image.mime_type};base64,{page_image.image_base64}",
                            "detail": "low",  # Use low detail for indexing
                        },
                    },
                ],
            }
        ]

        log_ctx = logger.bind(
            project_id=project_id, stage="page_indexing", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-page-{page_image.page_number}",
                stage_name="page_indexing",
                project_id=project_id,
            )

            # Parse JSON response
            import json

            parsed = json.loads(response_text.strip())

            # Validate and create PageIndexItem
            page_item = PageIndexItem(
                page_number=page_image.page_number,
                sheet_id=parsed.get("sheet_id"),
                sheet_title=parsed.get("sheet_title"),
                page_types=parsed.get("page_types", []),
                indicators=parsed.get("indicators", []),
                confidence=parsed.get("confidence", 0.5),
            )

            page_item = self._augment_window_signals(page_item)

            log_ctx.debug(
                f"Page {page_image.page_number}: types={page_item.page_types}, "
                f"indicators={len(page_item.indicators)}, confidence={page_item.confidence:.2f}"
            )

            return page_item

        except Exception as e:
            log_ctx.error(f"Failed to index page {page_image.page_number}: {e}")
            raise

    def _create_indexing_prompt(self) -> str:
        """Create prompt for page indexing."""
        return """You are analyzing a single page from a construction document.

Your task is to classify this page ONLY. Do NOT extract values, dimensions, or scope.

Answer these questions:

1. Is there a visible sheet number/ID? (e.g., "A-1", "S-2", "D-3")
2. Is there a visible sheet title? (e.g., "Front Elevation", "Typical Detail")
3. What type(s) of page is this? (can be multiple):
   - plan (floor plan, site plan)
   - elevation (building elevation)
   - detail (construction detail, section)
   - schedule (room schedule, door schedule, lintel schedule)
   - notes (general notes, specifications)
   - compliance (code compliance, permits)
   - cover (cover sheet)
   - index (drawing index)
   - unknown (cannot determine)
   - If you see tabular data listing window/door marks (e.g., columns for "Mark", "Type", "Width", "Height", "Qty" with entries like "W-1", "WP-101", "CW-1"), you MUST include "schedule" in page_types.

4. What key construction indicators are visible? (list any found):
   - dimensions (dimension lines, measurements)
   - lintel (lintel details, schedules, callouts)
   - parapet (parapet details, callouts)
   - flashing (flashing details)
   - room_schedule (room areas, schedules)
   - compliance (code references, permits)
   - window_schedule (window or door & window schedules, glazing schedules)
   - glazing (IG units, insulated glass, low-E notes, glass performance tables)
   - storefront (storefront or curtain wall system diagrams, frame tags, mullions)
   - window_detail (head/sill/jamb/window detail callouts or typical window sections)
   - window_tag (callouts or annotations like "W-1", "WP-101", "CW-1", "Vision Panel", "IG UNIT")

Return ONLY valid JSON matching this schema:

{
  "sheet_id": "A-1" or null,
  "sheet_title": "Front Elevation" or null,
  "page_types": ["elevation", "detail"],
  "indicators": ["dimensions", "lintel"],
  "confidence": 0.85
}

Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _select_fast_mode_candidate_pages(
        self, total_pages: int, max_pages: int, stride: int
    ) -> set[int]:
        """
        Select candidate pages for fast mode initial sampling.
        
        Strategy:
        - First 20 pages
        - Last 20 pages
        - Every Nth page (stride)
        - Stratified buckets from middle
        
        Args:
            total_pages: Total number of pages
            max_pages: Maximum candidate pages to select
            stride: Stride for sampling (every Nth page)
            
        Returns:
            Set of 1-indexed page numbers
        """
        candidates: set[int] = set()
        
        # First 20 pages
        first_count = min(20, total_pages)
        candidates.update(range(1, first_count + 1))
        
        # Last 20 pages
        if total_pages > first_count:
            last_count = min(20, total_pages - first_count)
            candidates.update(range(max(total_pages - last_count + 1, first_count + 1), total_pages + 1))
        
        # Every Nth page (stride sampling)
        for page_num in range(1, total_pages + 1, stride):
            candidates.add(page_num)
        
        # Stratified buckets from middle (ensure coverage)
        if total_pages > 40:
            middle_start = first_count + 1
            middle_end = total_pages - last_count if total_pages > 40 else total_pages
            middle_range = middle_end - middle_start + 1
            num_buckets = min(10, (max_pages - len(candidates)) // 2)
            
            if num_buckets > 0 and middle_range > 0:
                bucket_size = middle_range / num_buckets
                for i in range(num_buckets):
                    bucket_center = int(middle_start + (i + 0.5) * bucket_size)
                    candidates.add(bucket_center)
        
        # Clamp to max_pages (prioritize first/last, then stride, then stratified)
        if len(candidates) > max_pages:
            # Sort and take first max_pages
            sorted_candidates = sorted(candidates)
            # Prefer keeping first/last pages and stride pages
            priority_pages = set(range(1, min(20, total_pages) + 1))
            priority_pages.update(range(max(1, total_pages - 19), total_pages + 1))
            stride_pages = set(range(1, total_pages + 1, stride))
            priority_pages.update(stride_pages)
            
            # Keep priority pages first, then fill remaining slots
            selected = sorted(priority_pages.intersection(candidates))
            remaining_slots = max_pages - len(selected)
            if remaining_slots > 0:
                other_pages = sorted(candidates - priority_pages)
                selected.extend(other_pages[:remaining_slots])
            candidates = set(sorted(selected)[:max_pages])
        
        return candidates

    @staticmethod
    def _augment_window_signals(page_item: PageIndexItem) -> PageIndexItem:
        """Inject window-related indicators/page types from sheet metadata."""

        title = (page_item.sheet_title or "").lower()
        sheet_id = (page_item.sheet_id or "").lower()

        indicators = set(page_item.indicators)
        page_types = set(page_item.page_types)

        def _matches(text: str, keywords: tuple[str, ...]) -> bool:
            return any(keyword in text for keyword in keywords)

        window_keywords = ("window", "glazing", "fenestration", "storefront", "curtain")
        schedule_keywords = (
            "window schedule",
            "door & window",
            "door and window",
            "glazing schedule",
        )

        # Promote schedule detection when titles reference window schedules
        if _matches(title, schedule_keywords):
            indicators.add("window_schedule")
            page_types.add("schedule")

        # General window cues from titles or sheet IDs
        if _matches(title, window_keywords) or _matches(sheet_id, ("w-", "wp-", "cw-")):
            indicators.update({"window_detail", "window_tag", "window_schedule"})
            if "schedule" not in page_types:
                page_types.add("schedule")
            if "detail" not in page_types and "plan" not in page_types:
                page_types.add("detail")

        # Sheet IDs that start with "e" often carry elevations (e.g., "E-6")
        if sheet_id.startswith("e"):
            page_types.add("elevation")

        if sheet_id == "e-6":
            logger.debug(
                "Window augmentation debug for sheet E-6",
                page_number=page_item.page_number,
                page_types=sorted(page_types),
                indicators=sorted(indicators),
            )

        return PageIndexItem(
            page_number=page_item.page_number,
            sheet_id=page_item.sheet_id,
            sheet_title=page_item.sheet_title,
            page_types=sorted(page_types),
            indicators=sorted(indicators),
            confidence=page_item.confidence,
        )

    def _identify_hot_pages(self, indexed_pages: list[PageIndexItem]) -> list[int]:
        """
        Identify "hot pages" from indexed results.
        
        Hot pages are those with:
        - confidence >= 0.6
        - type in plan/elevation/detail/schedule/notes
        - OR indicators include dimensions/room_schedule/lintel/parapet/flashing
        
        Args:
            indexed_pages: List of indexed page items
            
        Returns:
            List of 1-indexed page numbers that are "hot"
        """
        hot_pages: list[int] = []
        
        relevant_types = {"plan", "elevation", "detail", "schedule", "notes"}
        relevant_indicators = {"dimensions", "room_schedule", "lintel", "parapet", "flashing", "compliance"}
        
        for page_item in indexed_pages:
            if page_item.confidence < 0.6:
                continue
            
            # Check if page has relevant types
            has_relevant_type = any(ptype in relevant_types for ptype in page_item.page_types)
            
            # Check if page has relevant indicators
            has_relevant_indicator = any(ind in relevant_indicators for ind in page_item.indicators)
            
            if has_relevant_type or has_relevant_indicator:
                hot_pages.append(page_item.page_number)
        
        return hot_pages

    def _expand_around_hot_pages(
        self,
        hot_pages: list[int],
        total_pages: int,
        radius: int,
        already_indexed: set[int],
        max_total_pages: int,
    ) -> set[int]:
        """
        Expand around hot pages by ±radius.
        
        Args:
            hot_pages: List of 1-indexed hot page numbers
            total_pages: Total number of pages
            radius: Expansion radius (±N pages)
            already_indexed: Set of already indexed page numbers (1-indexed)
            max_total_pages: Maximum total pages to index (for clamping)
            
        Returns:
            Set of 1-indexed page numbers to index (excluding already_indexed)
        """
        expansion_pages: set[int] = set()
        
        for hot_page in hot_pages:
            # Expand ±radius around hot page
            start_page = max(1, hot_page - radius)
            end_page = min(total_pages, hot_page + radius)
            
            for page_num in range(start_page, end_page + 1):
                if page_num not in already_indexed:
                    expansion_pages.add(page_num)
        
        # Clamp to max_total_pages (prioritize pages closer to hot pages)
        if len(already_indexed) + len(expansion_pages) > max_total_pages:
            # Sort by proximity to nearest hot page (closer = higher priority)
            def distance_to_nearest_hot(page_num: int) -> int:
                return min(abs(page_num - hp) for hp in hot_pages)
            
            sorted_expansion = sorted(expansion_pages, key=distance_to_nearest_hot)
            max_expansion = max_total_pages - len(already_indexed)
            expansion_pages = set(sorted_expansion[:max_expansion])
        
        return expansion_pages

