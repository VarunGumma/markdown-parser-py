from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import cast

import regex as re

from .blocks import iter_headings
from .node import MarkdownNode

NodePath = str | Sequence[str] | MarkdownNode
_NEWLINE = re.compile(r"\r\n|\r|\n")
# Conservative prefilter: false positives fall back to the full block parser.
_HEADING_CANDIDATE = re.compile(
    r"^ {0,3}(?:#{1,6}(?=[ \t]|$)|(?:=+|-+)[ \t]*$)", re.MULTILINE
)
# Fast path for documents whose non-heading lines start with ASCII letters.
# Other line starts can introduce block constructs, so they use CommonMark.
_NON_SIMPLE_LINE = re.compile(r"^(?!$|[A-Za-z]| {0,3}#{1,6}(?:[ \t]|$))", re.MULTILINE)
_SIMPLE_HEADING = re.compile(r"^ {0,3}(#{1,6})(?=[ \t]|$)[^\n]*(?:\n|$)", re.MULTILINE)
_LEADING_BLANK_LINES = re.compile(r"\A(?:[ \t]*(?:\r\n|\r|\n))+")


def _content_text(text: str) -> str:
    """Remove surrounding blank lines, without stripping content's trailing spaces."""
    last_nonblank = len(text.rstrip(" \t\r\n"))
    if not last_nonblank:
        return ""
    newline = _NEWLINE.search(text, last_nonblank)
    if newline is not None:
        text = text[: newline.start()]
    return cast(str, _LEADING_BLANK_LINES.sub("", text))


def _heading_title(heading: str, level: int, markup: str) -> str:
    # Derive titles from source, trimming only Markdown's ASCII whitespace.
    if markup.startswith("#"):
        text = heading.rstrip("\r\n").lstrip(" ")[level:].rstrip(" \t")
        if text.endswith("#"):
            without_hashes = text.rstrip("#")
            if without_hashes.endswith((" ", "\t")):
                text = without_hashes
        text = text.strip(" \t")
    else:
        lines = _NEWLINE.split(heading)
        if lines[-1] == "":
            lines.pop()
        text = "\n".join(lines[:-1]).strip(" \t\n")
    return text.replace("\0", "\ufffd")


def _front_matter_end(text: str, line_starts: list[int]) -> int:
    """Find a conventional initial YAML front matter block, if complete."""
    if len(line_starts) < 2:
        return 0
    first_line = text[line_starts[0] : line_starts[1]].rstrip("\r\n")
    if first_line.lstrip("\ufeff").rstrip(" \t") != "---":
        return 0
    for start, end in zip(line_starts[1:], line_starts[2:]):
        if text[start:end].rstrip("\r\n").rstrip(" \t") in ("---", "..."):
            return end
    return 0


def _path_parts(path: str | Sequence[str]) -> list[str]:
    if isinstance(path, str):
        return [] if not path else path.split(".")
    return list(path)


class MarkdownTree:
    """A tree of top-level Markdown headings and their raw section content."""

    def __init__(self) -> None:
        self.root: MarkdownNode = MarkdownNode(0, "ROOT")
        self._original_text = ""
        self._source_document: object | None = None
        self._front_matter = True

    def parse(self, markdown_text: str, *, front_matter: bool = True) -> None:
        """Replace this tree with sections parsed from *markdown_text*.

        Only headings at the document's top level form sections. Headings inside
        lists, block quotes, code blocks, and HTML blocks remain body content.
        A complete initial YAML front matter block is treated as body content
        by default. Set front_matter=False to scan without that convention.
        """
        # Simple ATX documents can be scanned directly. Ambiguous block
        # contexts use the in-package block scanner.
        heading_spans: Iterable[tuple[int, int, int, str]]
        if "\r" not in markdown_text and not _NON_SIMPLE_LINE.search(markdown_text):
            heading_spans = (
                (match.start(), match.end(), len(match.group(1)), match.group(1))
                for match in _SIMPLE_HEADING.finditer(markdown_text)
            )
        else:
            candidate_text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
            first_candidate = _HEADING_CANDIDATE.search(candidate_text)
            simple = first_candidate is None
            if first_candidate is not None and first_candidate.start() == 0:
                simple = (
                    _HEADING_CANDIDATE.search(candidate_text, first_candidate.end())
                    is None
                )
            if simple:
                first_newline = _NEWLINE.search(markdown_text)
                first_end = first_newline.end() if first_newline else len(markdown_text)
                heading_spans = (
                    iter_headings(markdown_text[:first_end])
                    if first_candidate is not None
                    else ()
                )
            else:
                front_matter_end = 0
                if front_matter and markdown_text.lstrip("\ufeff").startswith("---"):
                    line_starts = [
                        0,
                        *(match.end() for match in _NEWLINE.finditer(markdown_text)),
                    ]
                    if line_starts[-1] != len(markdown_text):
                        line_starts.append(len(markdown_text))
                    front_matter_end = _front_matter_end(markdown_text, line_starts)
                if front_matter_end:
                    heading_spans = (
                        (
                            start + front_matter_end,
                            end + front_matter_end,
                            level,
                            markup,
                        )
                        for start, end, level, markup in iter_headings(
                            markdown_text[front_matter_end:]
                        )
                    )
                else:
                    heading_spans = iter_headings(markdown_text)

        root = MarkdownNode(0, "ROOT")
        current = root
        stack = [root]
        body_start = 0
        current_heading = ""
        current_start = 0
        source_document = object()
        for start, end, level, markup in heading_spans:
            self._set_source(
                current,
                current_heading,
                markdown_text[body_start:start],
                source_document,
                current_start,
                start,
            )
            heading = markdown_text[start:end]
            title = _heading_title(heading, level, markup)
            while stack[-1].level >= level:
                stack.pop()
            node = MarkdownNode(level, title)
            # Nodes here are new and the stack already guarantees valid levels.
            parent = stack[-1]
            parent.children.append(node)
            node.parent = parent
            stack.append(node)
            current = node
            current_heading = heading
            current_start = start
            body_start = end
        self._set_source(
            current,
            current_heading,
            markdown_text[body_start:],
            source_document,
            current_start,
            len(markdown_text),
        )
        self.root = root
        self._original_text = markdown_text
        self._source_document = source_document
        self._front_matter = front_matter

    @staticmethod
    def _set_source(
        node: MarkdownNode,
        heading: str,
        body: str,
        document: object,
        start: int,
        end: int,
    ) -> None:
        content = _content_text(body)
        if content:
            node.content.append(content)
        # Keep the original spelling and spacing while the corresponding public
        # attributes remain unchanged. This allows exact unedited round trips.
        node._source_heading = heading
        node._source_body = body
        node._source_title = node.title
        node._source_level = node.level
        node._source_content = tuple(node.content)
        node._source_document = document
        node._source_start = start
        node._source_end = end

    def _iter_path(self, path: NodePath) -> Iterator[MarkdownNode]:
        if isinstance(path, MarkdownNode):
            node: MarkdownNode | None = path
            visited = set()
            while node is not None and id(node) not in visited:
                if node is self.root:
                    yield path
                    return
                visited.add(id(node))
                node = node.parent
            return

        def matching(
            nodes: Iterable[MarkdownNode], title: str
        ) -> Iterator[MarkdownNode]:
            for node in nodes:
                for child in node.children:
                    if child.title == title:
                        yield child

        nodes: Iterable[MarkdownNode] = (self.root,)
        for part in _path_parts(path):
            nodes = matching(nodes, part)
        yield from nodes

    def find_nodes_by_path(self, path: NodePath) -> list[MarkdownNode]:
        """Find all matches in document order.

        A sequence addresses titles containing dots, and an empty path names
        the root. A node handle is accepted if it belongs to this tree.
        """
        return list(self._iter_path(path))

    def find_node_by_path(self, path: NodePath) -> MarkdownNode | None:
        """Return the first full path match, or None when there is no match."""
        return next(self._iter_path(path), None)

    def _parent_for_path(self, path: NodePath) -> MarkdownNode | None:
        if isinstance(path, str) and path in ("", "ROOT"):
            return self.root
        return self.find_node_by_path(path)

    def remove_section(self, path: NodePath) -> bool:
        """Remove the first matching section; return whether it was found."""
        node = self.find_node_by_path(path)
        if node is not None and node.parent is not None:
            node.parent.remove_child(node)
            return True
        return False

    def add_section(
        self, parent_path: NodePath, title: str, content: str = ""
    ) -> MarkdownNode | None:
        """Append a section under the parent, or return None if it is missing.

        Raises ValueError if the title spans lines or a level-6 parent has no
        representable child heading level.
        """
        parent = self._parent_for_path(parent_path)
        if parent is None:
            return None
        if "\n" in title or "\r" in title:
            raise ValueError("a section title must fit on one line")
        if parent.level >= 6:
            raise ValueError("a level-6 heading cannot have a child section")
        node = MarkdownNode(parent.level + 1, title)
        if content:
            node.add_content(content)
        parent.add_child(node)
        return node

    def _inspect_tree(self) -> tuple[list[tuple[int, str]], bool]:
        """Validate structure and check whether all source sections are intact."""
        root = self.root
        source_document = root._source_document
        unchanged = (
            source_document is not None
            and source_document is self._source_document
            and root._source_heading is not None
            and root._source_body is not None
            and root._source_start == 0
            and root.title == root._source_title
            and root.level == root._source_level
            and tuple(root.content) == root._source_content
        )
        source_end = root._source_end
        found: list[tuple[int, str]] = []
        pending = [(node, self.root) for node in reversed(self.root.children)]
        stack = [self.root]
        seen = {id(self.root)}
        if self.root.level != 0 or self.root.parent is not None:
            raise ValueError("the root must have level 0 and no parent")
        while pending:
            node, parent = pending.pop()
            if id(node) in seen or node.parent is not parent:
                raise ValueError("the tree contains a cycle or inconsistent parent")
            seen.add(id(node))
            if not 1 <= node.level <= 6:
                raise ValueError("heading levels must be between 1 and 6")
            while stack[-1].level >= node.level:
                stack.pop()
            if stack[-1] is not parent:
                raise ValueError("heading levels do not represent the tree hierarchy")
            stack.append(node)
            if unchanged:
                unchanged = (
                    node._source_document is source_document
                    and node._source_heading is not None
                    and node._source_body is not None
                    and node._source_start == source_end
                    and node.title == node._source_title
                    and node.level == node._source_level
                    and tuple(node.content) == node._source_content
                )
                source_end = node._source_end
            found.append((node.level, node.title))
            pending.extend((child, node) for child in reversed(node.children))
        return found, unchanged and source_end == len(self._original_text)

    def _heading_signature(self) -> list[tuple[int, str]]:
        return self._inspect_tree()[0]

    def dump(self, *, validate: bool = True) -> str:
        """Return Markdown, preserving unedited source text and formatting.

        By default, validate the hierarchy and check edited output by reparsing
        it. Set validate=False to skip these checks when they are unnecessary.
        """
        expected = None
        if validate:
            expected, unchanged = self._inspect_tree()
            if unchanged:
                return self._original_text
        result = self.root.dump()
        if validate and result != self._original_text:
            reparsed = MarkdownTree()
            reparsed.parse(result, front_matter=self._front_matter)
            if expected != reparsed._heading_signature():
                raise ValueError(
                    "serialized Markdown does not preserve the section hierarchy"
                )
        return result

    def visualize(self) -> None:
        """Print heading hierarchy as a tree."""
        self.root.print_tree()

    def attach_subtree(
        self,
        target_path: NodePath,
        source_tree: MarkdownTree,
        source_path: NodePath | None = None,
        max_level: int = 6,
    ) -> list[MarkdownNode]:
        """Clone sections under a target, preserving relative heading levels.

        All sections must fit within *max_level* (1 through 6); otherwise no
        sections are attached and ValueError is raised.
        """
        if isinstance(max_level, bool) or not isinstance(max_level, int):
            raise TypeError("max_level must be an integer")
        if not 1 <= max_level <= 6:
            raise ValueError("max_level must be between 1 and 6")
        parent = self._parent_for_path(target_path)
        if parent is None:
            return []
        if source_path is None or (
            isinstance(source_path, str) and source_path in ("", "ROOT")
        ):
            source_nodes = list(source_tree.root.children)
        else:
            node = source_tree.find_node_by_path(source_path)
            if node is None:
                return []
            source_nodes = list(node.children) if node is source_tree.root else [node]

        # Validate and clone every source before mutating the destination. This
        # also handles attaching a tree to itself or one of its descendants.
        clones = []
        for source in source_nodes:
            delta = parent.level + 1 - source.level
            pending = [source]
            while pending:
                current = pending.pop()
                level = current.level + delta
                if level != current.level and (
                    "\n" in current.title or "\r" in current.title
                ):
                    raise ValueError("cannot relevel a multiline heading")
                if level < 1 or level > max_level:
                    raise ValueError(
                        "the subtree does not fit within the heading level limit"
                    )
                if any(child.level <= current.level for child in current.children):
                    raise ValueError("subtree heading levels must increase with depth")
                pending.extend(current.children)
            clones.append(source.copy_with_level_delta(delta, max_level=max_level))
        for clone in clones:
            parent.add_child(clone)
        return clones
