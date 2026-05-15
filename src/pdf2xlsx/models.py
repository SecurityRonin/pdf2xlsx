from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractedTable:
    page: int
    index: int
    rows: list[list[Any]]
    source: str

    @property
    def sheet_name(self) -> str:
        name = f"Table {self.index + 1} (p.{self.page})"
        return name[:31]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        if not self.rows:
            return 0
        return max(len(row) for row in self.rows)

    @property
    def is_empty(self) -> bool:
        return self.row_count <= 1
