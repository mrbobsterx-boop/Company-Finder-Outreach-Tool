"""Abstract discovery interface.

OSM/Overpass is the default (free) implementation, but nothing else in the
codebase should import OSMDiscoveryProvider directly outside of the CLI's
provider-selection code — that's what keeps a future paid provider (Google
Places, Yelp Fusion, ...) a drop-in swap instead of a rewrite.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from storage.models import Company


class DiscoveryProvider(ABC):
    @abstractmethod
    def search(
        self,
        country: str,
        region: Optional[str],
        city: Optional[str],
        category: str,
    ) -> List[Company]:
        """Return companies matching the given location and business category."""
        raise NotImplementedError
