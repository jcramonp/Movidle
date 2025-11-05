from abc import ABC, abstractmethod
from typing import Iterable

class ReportGenerator(ABC):
    content_type: str
    extension: str

    @abstractmethod
    def generate(self, peliculas: Iterable) -> bytes:
        """Devuelve el archivo del reporte como bytes."""
        ...
