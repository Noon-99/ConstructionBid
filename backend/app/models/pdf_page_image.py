"""PDF page image model for analysis."""

from pydantic import BaseModel, Field


class PdfPageImage(BaseModel):
    """Represents a single PDF page as an image for analysis."""

    page_number: int = Field(description="1-indexed page number")
    image_base64: str = Field(description="Base64-encoded image data")
    mime_type: str = Field(default="image/png", description="MIME type of the image")

