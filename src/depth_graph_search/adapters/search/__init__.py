"""Search adapters — exports DefaultSearchPipeline and DefaultEntityResolutionStrategy."""

from depth_graph_search.adapters.search.entity_resolution import DefaultEntityResolutionStrategy
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline

__all__ = ["DefaultSearchPipeline", "DefaultEntityResolutionStrategy"]
