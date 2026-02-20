from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportContext:
    domain: str
    start_date: date
    end_date: date
    country: str = "at"
    device: str = "mobile"  # wir verwenden in SISTRIX den Parameter mobile=1
