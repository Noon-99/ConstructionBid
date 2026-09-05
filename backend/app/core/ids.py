"""Project ID generation utilities."""

import uuid


def generate_project_id() -> str:
    """Generate a short UUID for project identification."""
    return str(uuid.uuid4())[:8]

