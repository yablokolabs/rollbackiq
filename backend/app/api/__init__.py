"""Control-plane HTTP surface.

``incident_api`` is the read-only evidence API the dashboard consumes. It is the
only HTTP surface in the project: it reads the artifacts the pipeline and the
Duo flow wrote and serves them, and it never mutates anything.
"""

from .incident_api import create_app

__all__ = ["create_app"]
