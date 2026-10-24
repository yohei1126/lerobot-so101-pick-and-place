"""Strip .en.md / .ja.md link suffixes so mkdocs-static-i18n can resolve pages."""

from __future__ import annotations

import re

_LINK = re.compile(
    r"(\[[^\]]*\]\()([^)\s]+?)\.(en|ja)\.md(#[^)]*)?(\))"
)


def on_page_markdown(markdown: str, **kwargs) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}.md{match.group(4) or ''}{match.group(5)}"

    return _LINK.sub(repl, markdown)
