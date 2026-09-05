"""PDF export service using Playwright (Phase 6.4)."""

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

from app.core.config import Settings

if TYPE_CHECKING:
    pass


class PDFExporter:
    """Service for generating PDFs from frontend proposal pages."""

    def __init__(self, settings: Settings) -> None:
        """Initialize PDF exporter."""
        self.settings = settings
        self.frontend_base_url = settings.frontend_base_url.rstrip("/")

    def generate_proposal_pdf(self, project_id: str) -> Path:
        """
        Generate a PDF from the proposal page.

        Args:
            project_id: Project ID

        Returns:
            Path to generated PDF file

        Raises:
            Exception: If PDF generation fails
        """
        log_ctx = logger.bind(project_id=project_id, service="pdf_exporter")
        log_ctx.info("Starting PDF generation")

        # Build URL with print=1 and highlights=1 query params (Phase 10.4)
        proposal_url = f"{self.frontend_base_url}/projects/{project_id}/proposal?print=1&highlights=1"
        log_ctx.info(f"Using frontend URL: {proposal_url}")

        # Output path: use out/ directory to match artifact convention
        output_dir = Path("out") / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "proposal.pdf"

        log_ctx.info(f"Generating PDF from URL: {proposal_url}, saving to: {pdf_path}")

        try:
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                )

                # Create page
                page = context.new_page()

                # Navigate to proposal page
                log_ctx.debug(f"Navigating to {proposal_url}")
                page.goto(proposal_url, wait_until="networkidle", timeout=30000)

                # Wait for proposal-ready marker (strict: fail if not ready)
                log_ctx.debug("Waiting for proposal-ready marker (timeout: 30s)")
                try:
                    page.wait_for_selector("#proposal-ready[data-ready='true']", timeout=30000)
                    log_ctx.debug("Proposal-ready marker found")
                except PlaywrightTimeoutError:
                    error_msg = "Proposal page did not reach ready state within timeout (30s). Page may still be loading data."
                    log_ctx.error(error_msg)
                    raise RuntimeError(error_msg) from None

                # Emulate print media
                page.emulate_media(media="print")

                # Generate PDF
                log_ctx.debug("Generating PDF")
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",  # US letter size
                    print_background=True,
                    margin={
                        "top": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.75in",
                        "right": "0.75in",
                    },
                )

                browser.close()

            log_ctx.info(f"PDF generated successfully: {pdf_path}")
            return pdf_path

        except Exception as e:
            log_ctx.exception(f"Failed to generate PDF: {e}")
            raise RuntimeError(f"PDF generation failed: {e}") from e

    def generate_trade_package_pdf(self, project_id: str, trade_id: str) -> Path:
        """
        Generate a PDF for a specific trade package (Phase 11.0).

        Args:
            project_id: Project ID
            trade_id: Trade package ID (e.g., 'masonry', 'metals')

        Returns:
            Path to generated PDF file

        Raises:
            Exception: If PDF generation fails
        """
        log_ctx = logger.bind(project_id=project_id, trade_id=trade_id, service="pdf_exporter")
        log_ctx.info(f"Starting trade package PDF generation for {trade_id}")

        # Build URL with trade package query param
        proposal_url = f"{self.frontend_base_url}/projects/{project_id}/proposal?print=1&trade_package={trade_id}"
        log_ctx.info(f"Using frontend URL: {proposal_url}")

        # Output path
        output_dir = Path("out") / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize trade_id for filename
        safe_trade_id = trade_id.replace(" ", "_").replace("/", "_")
        pdf_path = output_dir / f"trade_package_{safe_trade_id}.pdf"

        log_ctx.info(f"Generating trade package PDF from URL: {proposal_url}, saving to: {pdf_path}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                )
                page = context.new_page()

                log_ctx.debug(f"Navigating to {proposal_url}")
                page.goto(proposal_url, wait_until="networkidle", timeout=30000)

                # Wait for proposal-ready marker
                log_ctx.debug("Waiting for proposal-ready marker (timeout: 30s)")
                try:
                    page.wait_for_selector("#proposal-ready[data-ready='true']", timeout=30000)
                    log_ctx.debug("Proposal-ready marker found")
                except PlaywrightTimeoutError:
                    error_msg = "Proposal page did not reach ready state within timeout (30s)."
                    log_ctx.error(error_msg)
                    raise RuntimeError(error_msg) from None

                page.emulate_media(media="print")

                log_ctx.debug("Generating PDF")
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",
                    print_background=True,
                    margin={
                        "top": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.75in",
                        "right": "0.75in",
                    },
                )

                browser.close()

            log_ctx.info(f"Trade package PDF generated successfully: {pdf_path}")
            return pdf_path

        except Exception as e:
            log_ctx.exception(f"Failed to generate trade package PDF: {e}")
            raise RuntimeError(f"Trade package PDF generation failed: {e}") from e

    def generate_contractor_proposal_pdf(self, project_id: str) -> Path:
        """
        Generate a PDF from the contractor proposal page (Phase 9.6).

        Args:
            project_id: Project ID

        Returns:
            Path to generated PDF file

        Raises:
            Exception: If PDF generation fails
        """
        log_ctx = logger.bind(project_id=project_id, service="pdf_exporter")
        log_ctx.info("Starting contractor proposal PDF generation")

        # Build URL with print=1 query param
        proposal_url = f"{self.frontend_base_url}/projects/{project_id}/contractor-proposal?print=1"
        log_ctx.info(f"Using frontend URL: {proposal_url}")

        # Output path: use out/ directory to match artifact convention
        output_dir = Path("out") / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "contractor_proposal.pdf"

        log_ctx.info(f"Generating PDF from URL: {proposal_url}, saving to: {pdf_path}")

        try:
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                )

                # Create page
                page = context.new_page()

                # Navigate to contractor proposal page
                log_ctx.debug(f"Navigating to {proposal_url}")
                page.goto(proposal_url, wait_until="networkidle", timeout=30000)

                # Wait for proposal-ready marker (strict: fail if not ready)
                log_ctx.debug("Waiting for contractor-proposal-ready marker (timeout: 30s)")
                try:
                    page.wait_for_selector("#contractor-proposal-ready[data-ready='true']", timeout=30000)
                    log_ctx.debug("Contractor proposal-ready marker found")
                except PlaywrightTimeoutError:
                    error_msg = "Contractor proposal page did not reach ready state within timeout (30s). Page may still be loading data."
                    log_ctx.error(error_msg)
                    raise RuntimeError(error_msg) from None

                # Emulate print media
                page.emulate_media(media="print")

                # Generate PDF
                log_ctx.debug("Generating PDF")
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",  # US letter size
                    print_background=True,
                    margin={
                        "top": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.75in",
                        "right": "0.75in",
                    },
                )

                browser.close()

            log_ctx.info(f"PDF generated successfully: {pdf_path}")
            return pdf_path

        except Exception as e:
            log_ctx.exception(f"Failed to generate contractor proposal PDF: {e}")
            raise RuntimeError(f"Contractor proposal PDF generation failed: {e}") from e

