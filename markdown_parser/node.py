from __future__ import annotations

import regex as re

_BLANK_LINE_END = re.compile(r"(?:\r\n|\r|\n)[ \t]*(?:\r\n|\r|\n)\Z")
_BLANK_LINE_IN_PROGRESS = re.compile(r"(?:\r\n|\r|\n)[ \t]+\Z")


class MarkdownNode:
    def __init__(
        self, level: int, title: str, parent: MarkdownNode | None = None
    ) -> None:
        self.level: int = level  # Heading level (0=root, 1=#, etc.)
        self.title: str = title  # Heading text, as Markdown
        self.content: list[str] = []
        self.children: list[MarkdownNode] = []
        self.parent: MarkdownNode | None = None

        # Source metadata is private; public attributes remain editable.
        self._source_heading: str | None = None
        self._source_body: str | None = None
        self._source_title: str | None = None
        self._source_level: int | None = None
        self._source_content: tuple[str, ...] | None = None
        self._source_document: object | None = None
        self._source_start = 0
        self._source_end = 0
        if parent is not None:
            if not isinstance(parent, MarkdownNode):
                raise TypeError("parent must be a MarkdownNode or None")
            parent.add_child(self)

    def add_child(self, node: MarkdownNode) -> None:
        """Attach or move a child; reject cycles. Levels are not adjusted."""
        if not isinstance(node, MarkdownNode):
            raise TypeError("child must be a MarkdownNode")
        ancestor: MarkdownNode | None = self
        visited = set()
        while ancestor is not None:
            if ancestor is node:
                raise ValueError("cannot add a node to itself or its descendant")
            if id(ancestor) in visited:
                raise ValueError("existing parent chain contains a cycle")
            visited.add(id(ancestor))
            ancestor = ancestor.parent
        if node.parent is self:
            return
        if not self.level < node.level <= 6:
            raise ValueError(
                "child heading level must be greater than its parent and at most 6"
            )
        if self.children and self.children[-1].level < node.level:
            raise ValueError("a later sibling cannot have a deeper heading level")
        if node.parent is not None:
            node.parent.remove_child(node)
        self.children.append(node)
        node.parent = self

    def add_content(self, text: str) -> None:
        """Add content without discarding significant trailing spaces."""
        if text:
            self.content.append(text)

    def remove_child(self, node: MarkdownNode) -> None:
        """Detach a direct child, raising ValueError if it is not present."""
        for index, child in enumerate(self.children):
            if child is node:
                del self.children[index]
                if node.parent is self:
                    node.parent = None
                return
        raise ValueError("node is not a child of this parent")

    def dump(self) -> str:
        """Serialize a subtree, retaining unchanged source spelling and spacing."""
        parts: list[str] = []
        tail = ""
        previous_document: object | None = None
        previous_end: int | None = None

        def append(text: str) -> None:
            nonlocal tail
            if text:
                parts.append(text)
                tail = text[-256:] if len(text) >= 256 else (tail + text)[-256:]

        def separate_sections() -> None:
            if not tail or _BLANK_LINE_END.search(tail):
                return
            if _BLANK_LINE_IN_PROGRESS.search(tail) or tail.endswith(("\r", "\n")):
                append("\n")
            else:
                append("\n\n")

        def write(node: MarkdownNode) -> None:
            nonlocal previous_document, previous_end
            same_heading = (
                node._source_heading is not None
                and node.title == node._source_title
                and node.level == node._source_level
            )
            same_body = (
                node._source_body is not None
                and tuple(node.content) == node._source_content
            )
            if node.level > 0:
                contiguous = (
                    same_heading
                    and previous_document is not None
                    and previous_document is node._source_document
                    and previous_end == node._source_start
                )
                if not contiguous:
                    separate_sections()
                if same_heading:
                    heading = node._source_heading or ""
                else:
                    # A multiline Setext title cannot always be represented
                    # as one ATX line without changing inline Markdown.
                    if "\n" in node.title or "\r" in node.title:
                        raise ValueError("cannot serialize a changed multiline heading")
                    title = node.title
                    heading = "#" * node.level + (" " + title if title else "")
                    # A closing marker keeps a title ending in # from being
                    # interpreted as the heading's closing marker itself.
                    if title.endswith("#"):
                        heading += " ##"
                append(heading)
            else:
                heading = ""

            if same_body:
                body = node._source_body or ""
                if heading and body and not heading.endswith(("\r", "\n")):
                    if not body.startswith(("\r", "\n")):
                        append("\n")
                append(body)
            elif node.content:
                if heading:
                    append("\n" if heading.endswith(("\r", "\n")) else "\n\n")
                append("\n".join(node.content))

            if same_heading and same_body and node._source_document is not None:
                previous_document = node._source_document
                previous_end = node._source_end
            else:
                previous_document = None
                previous_end = None
            for child in node.children:
                write(child)

        write(self)
        return "".join(parts)

    def print_tree(self, indent: str = "", last: bool = True) -> None:
        """Print a tree-like structure of headings similar to Linux `tree`."""
        prefix = indent + ("└── " if last else "├── ")
        if self.level > 0:
            print(prefix + f"{'#' * self.level} {self.title}")
        for i, child in enumerate(self.children):
            next_indent = indent + ("    " if last else "│   ")
            child.print_tree(next_indent, i == len(self.children) - 1)

    def copy_with_level_delta(self, delta: int, max_level: int = 6) -> MarkdownNode:
        """Deep-copy with shifted levels, rejecting unrepresentable headings."""
        if isinstance(delta, bool) or not isinstance(delta, int):
            raise TypeError("delta must be an integer")
        if isinstance(max_level, bool) or not isinstance(max_level, int):
            raise TypeError("max_level must be an integer")
        if not 1 <= max_level <= 6:
            raise ValueError("max_level must be between 1 and 6")

        def copy(node: MarkdownNode) -> MarkdownNode:
            new_level = 0 if node.level == 0 else node.level + delta
            if new_level != node.level and ("\n" in node.title or "\r" in node.title):
                raise ValueError("cannot relevel a multiline heading")
            if node.level != 0 and not 1 <= new_level <= max_level:
                raise ValueError(
                    "the subtree does not fit within the heading level limit"
                )
            clone = MarkdownNode(new_level, node.title)
            clone.content = list(node.content)
            clone._source_heading = node._source_heading
            clone._source_body = node._source_body
            clone._source_title = node._source_title
            clone._source_level = node._source_level
            clone._source_content = node._source_content
            clone._source_document = node._source_document
            clone._source_start = node._source_start
            clone._source_end = node._source_end
            for child in node.children:
                clone.add_child(copy(child))
            return clone

        return copy(self)
