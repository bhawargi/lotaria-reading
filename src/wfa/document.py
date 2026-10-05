from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Metadata:
    title: str | None = None
    author: str | None = None
    language: str | None = None
    source: str = "plain"  # "gutenberg" | "epub" | "plain"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Section:
    title: str | None
    text: str  # cleaned text, original case kept


@dataclass
class Document:
    path: str
    file_hash: str
    format: str  # "txt" | "epub"
    metadata: Metadata
    sections: list[Section] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)  # lowercased, filtered
    lemmas: list[str] | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)  # {"rule", "section", "text"} per cut

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        data = dict(data)
        data["metadata"] = Metadata(**data["metadata"])
        data["sections"] = [Section(**s) for s in data["sections"]]
        return cls(**data)
