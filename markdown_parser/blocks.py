"""Find top-level CommonMark headings without parsing inline Markdown.

Offsets are Python string indices into the original input.  The end offset is
exclusive and includes the final line ending, if present.  Setext spans include
all paragraph lines and the underline.  Front matter is deliberately not
special: callers that support it must mask it before invoking this scanner.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import regex as re

_NEWLINE = re.compile(r"\r\n|\r|\n")
_ATX = re.compile(r"^(#{1,6})(?= |$)")
_SETEXT = re.compile(r"^(=+|-+) *$")
_THEMATIC = re.compile(r"^(?:\*(?: *\*){2,}|-(?: *-){2,}|_(?: *_){2,}) *$")
_LIST = re.compile(r"^([*+-]|[0-9]{1,9}[.)])(?= |$)")
_FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_BLOCK_TAGS = (
    "address article aside base basefont blockquote body caption center col "
    "colgroup dd details dialog dir div dl dt fieldset figcaption figure footer "
    "form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li "
    "link main menu menuitem nav noframes ol optgroup option p param search "
    "section summary table tbody td tfoot th thead title tr track ul"
).split()
_HTML_BLOCK = re.compile(
    r"^</?(?:" + "|".join(_BLOCK_TAGS) + r")(?:[ \t]|/?>|$)", re.I | re.ASCII
)
_HTML_RAW = re.compile(r"^<(?:script|pre|style|textarea)(?:[ \t>]|$)", re.I | re.ASCII)
_HTML_RAW_END = re.compile(r"</(?:script|pre|style|textarea)>", re.I | re.ASCII)
_HTML_DECL = re.compile(r"^<![A-Za-z]")
_ATTRIBUTE = (
    r"[A-Za-z_:][A-Za-z0-9:._-]*(?: *= *(?:[^ \"'=<>`\x00-\x20]+|'[^']*'|\"[^\"]*\"))?"
)
_HTML_TAG = re.compile(
    r"^(?:<[A-Za-z][A-Za-z0-9-]*(?: +"
    + _ATTRIBUTE
    + r")* */?>|</[A-Za-z][A-Za-z0-9-]* *>) *$"
)


@dataclass
class _Container:
    kind: str
    indent: int = 0
    empty: bool = False


def _lines(text: str) -> list[tuple[int, int, str]]:
    lines = []
    start = 0
    for match in _NEWLINE.finditer(text):
        content = text[start : match.start()].replace("\0", "\ufffd")
        lines.append((start, match.end(), content.expandtabs(4)))
        start = match.end()
    if start < len(text):
        content = text[start:].replace("\0", "\ufffd")
        lines.append((start, len(text), content.expandtabs(4)))
    return lines


def _indent(line: str, pos: int) -> int:
    return len(line[pos:]) - len(line[pos:].lstrip(" "))


def _html_start(
    content: str, interrupting: bool
) -> tuple[int, re.Pattern[str] | None] | None:
    if _HTML_RAW.match(content):
        return 1, _HTML_RAW_END
    if content.startswith("<!--"):
        return 2, re.compile(r"-->")
    if content.startswith("<?"):
        return 3, re.compile(r"\?>")
    if _HTML_DECL.match(content):
        return 4, re.compile(r">")
    if content.startswith("<![CDATA["):
        return 5, re.compile(r"\]\]>")
    if _HTML_BLOCK.match(content):
        return 6, None
    if not interrupting and _HTML_TAG.match(content):
        return 7, None
    return None


def _fence_start(content: str) -> tuple[str, int] | None:
    match = _FENCE.match(content)
    if not match:
        return None
    marker, info = match.groups()
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def _list_start(content: str, interrupting: bool) -> tuple[int, int, bool] | None:
    match = _LIST.match(content)
    if not match:
        return None
    marker = match.group(1)
    tail = content[match.end() :]
    empty = not tail.strip(" ")
    if interrupting and (empty or (len(marker) > 1 and int(marker[:-1]) != 1)):
        return None
    spaces = len(tail) - len(tail.lstrip(" "))
    padding = spaces if not empty and 1 <= spaces <= 4 else 1
    return match.end() + min(padding, spaces), len(marker) + padding, empty


def _interrupts(line: str, pos: int, *, container_boundary: bool = False) -> bool:
    indent = _indent(line, pos)
    if indent > 3:
        return False
    content = line[pos + indent :]
    return bool(
        _ATX.match(content)
        or _THEMATIC.match(content)
        or _fence_start(content)
        or content.startswith(">")
        or _list_start(content, not container_boundary)
        or _html_start(content, not container_boundary)
    )


def _reference_end(
    lines: list[tuple[int, int, str]],
    index: int,
    pos: int,
    containers: list[_Container],
) -> int | None:
    """Return the line after a link definition, including a multiline title.

    Definitions cannot interrupt a paragraph.  Read continuation lines only as
    needed, since a following line that looks like a title may instead belong
    to the next block.  Source positions are retained separately from this
    temporary, tab-expanded view.
    """
    if lines[index][2][pos : pos + 1] != "[":
        return None
    data = lines[index][2][pos:] + "\n"
    next_line = index + 1

    def char(at: int) -> str:
        nonlocal data, next_line
        while at >= len(data) and next_line < len(lines):
            line = lines[next_line][2]
            offset = 0
            for container in containers:
                indent = _indent(line, offset)
                if container.kind == "quote":
                    if indent > 3 or line[offset + indent : offset + indent + 1] != ">":
                        break
                    offset += indent + 1
                    if line[offset : offset + 1] == " ":
                        offset += 1
                elif indent >= container.indent:
                    offset += container.indent
                else:
                    break
            if not line[offset:].strip(" ") or _interrupts(line, offset):
                next_line = len(lines)
                break
            indent = _indent(line, offset)
            if indent <= 3 and _SETEXT.match(line[offset + indent :]):
                next_line = len(lines)
                break
            data += line[offset:].lstrip(" ") + "\n"
            next_line += 1
        return data[at] if at < len(data) else ""

    # Link labels may span lines, but may not contain unescaped brackets.
    at = 1
    label: list[str] = []
    while True:
        ch = char(at)
        if not ch or ch == "[" or len(label) > 999:
            return None
        if ch == "]":
            break
        if ch == "\\" and char(at + 1) and char(at + 1) != "\n":
            label.append(ch + char(at + 1))
            at += 2
        else:
            label.append(ch)
            at += 1
    if not "".join(label).strip() or char(at + 1) != ":":
        return None
    at += 2
    while char(at) == " ":
        at += 1
    if char(at) == "\n":
        at += 1
        while char(at) == " ":
            at += 1

    # Destination: angle-bracket form, or balanced parentheses in a bare URL.
    if char(at) == "<":
        at += 1
        while char(at) not in ("", "\n", "<", ">"):
            at += 2 if char(at) == "\\" and char(at + 1) not in ("", "\n") else 1
        if char(at) != ">":
            return None
        at += 1
    else:
        beginning = at
        depth = 0
        while True:
            ch = char(at)
            if not ch or ord(ch) <= 32 or ord(ch) == 127:
                break
            if ch == "\\" and char(at + 1) not in ("", " ", "\n"):
                at += 2
                continue
            if ch == "(":
                depth += 1
                if depth > 32:
                    return None
            elif ch == ")":
                if not depth:
                    break
                depth -= 1
            at += 1
        if at == beginning or depth:
            return None

    destination_end = at
    while char(at) == " ":
        at += 1
    if char(at) == "\n":
        # If a title on the following line is invalid, keep the definition
        # ending at the destination instead of consuming that line.
        fallback = at
        at += 1
        while char(at) == " ":
            at += 1
    else:
        fallback = None
        if at == destination_end:
            return None

    opener = char(at)
    if opener in ('"', "'", "("):
        closer = ")" if opener == "(" else opener
        at += 1
        while char(at) and char(at) != closer:
            if opener == "(" and char(at) == "(":
                break
            if char(at) == "\\" and char(at + 1) not in ("", "\n"):
                at += 2
            else:
                at += 1
        if char(at) == closer:
            at += 1
            while char(at) == " ":
                at += 1
            if char(at) == "\n":
                return index + data.count("\n", 0, at) + 1
    if fallback is not None:
        return index + data.count("\n", 0, fallback) + 1
    return None


def iter_headings(text: str) -> Iterator[tuple[int, int, int, str]]:
    """Yield ``(start, end, level, markup)`` for top-level headings in *text*.

    ATX markup is the opening run of hashes; Setext markup is ``=`` or ``-``.
    Blocks nested in lists or block quotes are excluded.  Only CR, LF and CRLF
    are line endings; tabs are interpreted at four-column stops.
    """
    lines = _lines(text)
    containers: list[_Container] = []
    # leaf is one of paragraph, fence, code, html, or None.  Only a
    # top-level paragraph can become a heading returned by this function.
    leaf: str | None = None
    paragraph_start = 0
    fence_char = ""
    fence_length = 0
    html_end: re.Pattern[str] | None = None

    skip_until = -1
    definition_depth = -1
    for line_index, (start, end, line) in enumerate(lines):
        if line_index < skip_until:
            continue
        pos = 0
        matched = 0
        for container in containers:
            if container.kind == "quote":
                indent = _indent(line, pos)
                if indent > 3 or line[pos + indent : pos + indent + 1] != ">":
                    break
                pos += indent + 1
                if line[pos : pos + 1] == " ":
                    pos += 1
            else:
                rest_blank = not line[pos:].strip(" ")
                if rest_blank:
                    if container.empty and _indent(line, pos) < container.indent:
                        break
                    pos = len(line)
                else:
                    indent = _indent(line, pos)
                    if indent < container.indent:
                        break
                    pos += container.indent
                    container.empty = False
            matched += 1

        follows_definition = (
            line_index == skip_until
            and matched == definition_depth
            and matched == len(containers)
        )

        # A paragraph may continue lazily without the container prefixes.
        if matched < len(containers):
            if (
                leaf == "paragraph"
                and bool(line[pos:].strip(" "))
                and not _interrupts(line, pos, container_boundary=True)
            ):
                continue
            del containers[matched:]
            leaf = None

        blank = not line[pos:].strip(" ")
        if leaf == "fence":
            indent = _indent(line, pos)
            rest = line[pos + indent :]
            if indent <= 3 and re.fullmatch(
                re.escape(fence_char) + "{" + str(fence_length) + r",} *", rest
            ):
                leaf = None
            continue
        if leaf == "html":
            if html_end is None and blank:
                leaf = None
            else:
                if html_end is not None and html_end.search(line[pos:]):
                    leaf = None
                continue
        if leaf == "code":
            if blank or _indent(line, pos) >= 4:
                continue
            leaf = None
        if leaf == "paragraph":
            if blank:
                leaf = None
                continue
            indent = _indent(line, pos)
            content = line[pos + indent :]
            underline = _SETEXT.match(content) if indent <= 3 else None
            if underline:
                marker = underline.group(1)[0]
                if not containers:
                    yield paragraph_start, end, 1 if marker == "=" else 2, marker
                leaf = None
                continue
            if not _interrupts(line, pos):
                continue
            leaf = None

        # Definitions are removed from the beginning of a paragraph only
        # after block boundaries are known. The next non-interrupting line is
        # therefore still paragraph text, even if indented or list-like.
        if follows_definition and not blank:
            indent = _indent(line, pos)
            content = line[pos + indent :]
            next_definition = (
                _reference_end(lines, line_index, pos + indent, containers)
                if indent <= 3
                else None
            )
            if next_definition is not None:
                skip_until = next_definition
                definition_depth = len(containers)
                continue
            if (indent <= 3 and _SETEXT.match(content)) or not _interrupts(line, pos):
                leaf = "paragraph"
                paragraph_start = start
                continue

        # Open any containers, then identify the leaf block inside them.
        while True:
            indent = _indent(line, pos)
            content = line[pos + indent :]
            if not content:
                break
            if indent >= 4:
                leaf = "paragraph" if follows_definition else "code"
                if follows_definition:
                    paragraph_start = start
                break
            if _THEMATIC.match(content):
                break
            if content.startswith(">"):
                follows_definition = False
                pos += indent + 1
                if line[pos : pos + 1] == " ":
                    pos += 1
                containers.append(_Container("quote"))
                continue
            item = _list_start(content, False)
            if item:
                follows_definition = False
                consumed, width, empty = item
                pos += indent + consumed
                containers.append(_Container("list", indent + width, empty))
                continue
            atx = _ATX.match(content)
            if atx:
                markup = atx.group(1)
                if not containers:
                    yield start, end, len(markup), markup
                break
            fence = _fence_start(content)
            if fence:
                fence_char, fence_length = fence
                leaf = "fence"
                break
            html = _html_start(content, False)
            if html:
                kind, html_end = html
                if kind == 7 and follows_definition:
                    leaf = "paragraph"
                    paragraph_start = start
                    break
                if html_end is None or not html_end.search(content):
                    leaf = "html"
                break
            definition_end = _reference_end(lines, line_index, pos + indent, containers)
            if definition_end is not None:
                skip_until = definition_end
                definition_depth = len(containers)
                break
            leaf = "paragraph"
            paragraph_start = start
            break
