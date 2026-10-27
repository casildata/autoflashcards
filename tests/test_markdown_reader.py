from pathlib import Path

from autoflashcards.readers import read

FIXTURE = Path(__file__).parent / "fixtures" / "cells.md"


def test_block_kinds_and_heading_paths():
    blocks = read(FIXTURE)
    by_text = {b.text: b for b in blocks}

    assert by_text["Cell Biology"].kind == "heading"
    assert by_text["Cell Biology"].heading_path == ()
    assert by_text["Membrane Proteins"].heading_path == ("Cell Biology", "Transport")
    assert by_text["Cells are the basic unit of life."].kind == "paragraph"

    osmosis = by_text["Osmosis: movement of water across a semipermeable membrane."]
    assert osmosis.kind == "bullet"  # bold markers are stripped
    assert osmosis.heading_path == ("Cell Biology", "Transport")

    channel = by_text["Channel protein: forms a pore that lets specific ions pass."]
    assert channel.heading_path == ("Cell Biology", "Transport", "Membrane Proteins")

    # a sibling heading replaces the previous one at the same level
    assert by_text["Mitochondrion: the site of aerobic respiration."].heading_path == (
        "Cell Biology",
        "Organelles",
    )


def test_bold_lead():
    leads = {b.text: b.bold_lead for b in read(FIXTURE)}
    assert leads["Golgi apparatus packages proteins for transport out of the cell."] == (
        "Golgi apparatus"
    )
    assert leads["Osmosis: movement of water across a semipermeable membrane."] == "Osmosis"
    assert leads["Diffusion: net movement of particles from high to low concentration."] == ""


def test_code_blocks_are_skipped():
    assert not any("nucleus" in b.text for b in read(FIXTURE))


def test_source_is_file_name():
    assert {b.source for b in read(FIXTURE)} == {"cells.md"}
