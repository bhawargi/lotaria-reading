from wfa import Document, Metadata, Section


def make_document() -> Document:
    return Document(
        path="books/example.txt",
        file_hash="abc123",
        format="txt",
        metadata=Metadata(title="Example", author="Anon", language="en", extra={"year": 1900}),
        sections=[Section("One", "First chapter."), Section(None, "Second chapter.")],
        tokens=["first", "chapter", "second", "chapter"],
        stats={"tokens": 4},
        warnings=["test warning"],
    )


def test_round_trip_through_dict():
    doc = make_document()
    assert Document.from_dict(doc.to_dict()) == doc


def test_text_joins_sections():
    assert make_document().text == "First chapter.\n\nSecond chapter."
