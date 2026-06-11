"""SDK delivery surface — Python importable library for depth-graph-search.

Exposes the main facade and pipeline classes for direct use by Python developers:

    from depth_graph_search.sdk import GraphSearch
    from depth_graph_search.sdk import DefaultIngestionPipeline, DefaultSearchPipeline
"""

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.sdk.client import GraphSearch

__all__ = [
    "GraphSearch",
    "DefaultIngestionPipeline",
    "DefaultSearchPipeline",
]
