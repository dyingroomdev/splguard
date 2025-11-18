from splguard.templates import (
    MAX_LINE_LENGTH,
    render_contract_block,
    render_links_block,
    render_presale_block,
    render_quick_replies,
    render_team_cards,
)


def _assert_line_lengths(text: str) -> None:
    for line in text.splitlines():
        assert len(line) <= MAX_LINE_LENGTH


def test_team_cards_escape_markdown() -> None:
    message = render_team_cards(
        [
            {"name": "Aragorn *Lead*", "role": "Project Lead", "contact": "@aragornofficial"},
        ]
    )

    assert "\\*" in message  # escaped asterisk
    _assert_line_lengths(message)


def test_contract_block_contains_counter_and_link() -> None:
    text = render_contract_block(
        addresses=["So11111111111111111111111111111111111111112"],
        chain="Solana",
        token_ticker="SPLG",
        supply="10B",
        explorer_url="https://solscan.io/token/So1111",
    )

    assert "SPLG" in text
    assert "https://" in text
    assert "1\\)" in text
    assert "10B" in text
    _assert_line_lengths(text)


def test_presale_block_formats_dates_and_status() -> None:
    text = render_presale_block(
        status="active",
        project_name="SPL Shield",
        platform="PinkSale",
        link="https://sale.example",
        hardcap="1000",
        softcap="500",
        raised="250",
        start_time="2024-05-01T12:00:00+00:00",
        end_time="2024-05-02T12:00:00+00:00",
    )

    assert "🟢" in text
    assert "2024-05-01 12:00 UTC" in text
    assert "View Presale" in text
    _assert_line_lengths(text)


def test_links_block_title_casing() -> None:
    text = render_links_block({"twitter": "https://x.com/splshield"})
    assert "Twitter" in text
    assert "https://" in text


def test_quick_replies_is_markdown_safe() -> None:
    text = render_quick_replies()
    assert "Quick Replies" in text
    assert "seed phrase" in text
    _assert_line_lengths(text)
