from typing import Dict, Type
from .interfaces import ReportGenerator
from .csv_report import CsvReportGenerator
from .pdf_report import PdfReportGenerator

_REGISTRY: Dict[str, Type[ReportGenerator]] = {
    "csv": CsvReportGenerator,
    "pdf": PdfReportGenerator,
}

def get_report(kind: str) -> ReportGenerator:
    cls = _REGISTRY.get((kind or "").lower(), CsvReportGenerator)
    return cls()
