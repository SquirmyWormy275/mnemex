from pathlib import Path

STYLESHEET = (
    Path(__file__).parents[1] / "mnemex" / "results" / "static" / "results" / "results-desk.css"
)


def test_manual_entry_table_stacks_labeled_cells_on_mobile() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    _, manual_mobile_rules = css.rsplit("@media(max-width:700px)", maxsplit=1)

    assert ".table:has(input) thead{display:none}" in manual_mobile_rules
    assert ".table:has(input) tr{display:block" in manual_mobile_rules
    assert ".table:has(input) td{display:block" in manual_mobile_rules
    assert (
        ".table:has(input) td:before{content:attr(data-label);display:block" in manual_mobile_rules
    )


def test_existing_non_input_mobile_table_treatment_is_preserved() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")

    assert ".table:not(:has(input)) td{display:grid" in css
