"""B19: parsed sections carry the nearest markdown heading as section_ref, so the
evidence panel can show a page/heading reference. Offline — pure function."""

from __future__ import annotations

from app.services.parsing import _sections_from_markdown


def test_sections_tagged_with_nearest_heading():
    md = "# Intro\n\nHello world.\n\n## Details\n\nMore text here.\n\nEven more."
    refs = [(s.ref, s.text) for s in _sections_from_markdown(md)]

    assert ("Intro", "Hello world.") in refs
    assert ("Details", "More text here.") in refs
    assert ("Details", "Even more.") in refs  # ref carries forward until the next heading


def test_text_without_heading_has_no_ref():
    secs = _sections_from_markdown("Just a paragraph with no heading.")
    assert secs[0].ref is None
