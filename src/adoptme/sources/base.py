from __future__ import annotations

from abc import ABC, abstractmethod

from ..http import PoliteClient
from ..models import ValueRecord


class Source(ABC):
    """A site that publishes pet values. One subclass per extraction strategy."""

    def __init__(self, name: str, config: dict, client: PoliteClient) -> None:
        self.name = name
        self.config = config
        self.client = client

    @property
    def is_configured(self) -> bool:
        """False until pages/selectors have been filled in (see `probe`)."""
        return bool(self.config.get("pages"))

    @abstractmethod
    def fetch(self) -> list[ValueRecord]:
        """Return every value currently published by the source."""
