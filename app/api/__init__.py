"""HTTP API routers."""
from app.api import routes_admin, routes_documents, routes_health, routes_query

__all__ = ["routes_documents", "routes_query", "routes_admin", "routes_health"]
