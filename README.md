# markdown-parser-py

Parse a Markdown document into a heading tree, edit its sections, and write it back to Markdown. Unedited documents round-trip exactly as Python strings, including their preamble, heading syntax, blank lines, and line endings.

The package supports Python 3.10 and later. Its own block scanner identifies section headings and their surrounding Markdown.

## Installation

```bash
pip install markdown-parser-py
```

For development:

```bash
git clone https://github.com/VarunGumma/markdown-parser-py
cd markdown-parser-py
pip install -e .
```

## Parse and edit a document

```python
from markdown_parser import MarkdownTree

tree = MarkdownTree()
tree.parse("""Introduction before the first heading.

# Guide
A short guide.

## Installation
Run `pip install example`.
""")

installation = tree.find_node_by_path("Guide.Installation")
assert installation is not None
print(installation.content)

tree.add_section("Guide", "Usage", "Import and use the package.")
print(tree.dump())
tree.visualize()
```

`parse()` replaces the tree's previous contents. The synthetic root has level 0; headings have levels 1–6. Every node has a `title`, `level`, `content` list, `children` list, and `parent`. A heading belongs to the nearest preceding heading with a smaller level, even if levels are skipped. Text before the first heading belongs to the root.

A node's title is Markdown source, including inline formatting, rather than rendered plain text. ATX opening and closing markers and Setext underlines are excluded. Titles can be empty. Section content excludes child sections. Parsed `content` entries omit surrounding blank lines for convenient access, while unchanged source is retained separately for serialization. `add_content()` appends the supplied text as a new content entry; entries are joined with a newline when edited content is written.

## Find sections

Dot paths select titles from the root downward. A missing path returns `None`:

```python
node = tree.find_node_by_path("Guide.Installation")
```

Use a sequence for a title containing a literal dot, or for a top-level section named `ROOT`:

```python
node = tree.find_node_by_path(["Version 1.0", "Installation"])
```

`find_nodes_by_path(path)` returns all complete matches in document order. `find_node_by_path(path)` and mutators taking a path choose the first complete match. To edit a particular duplicate, pass the returned node directly:

```python
matches = tree.find_nodes_by_path(["Repeated heading"])
if len(matches) > 1:
    tree.add_section(matches[1], "Child", "Text")
    tree.remove_section(matches[0])
```

An empty string or empty sequence refers to the root. For `add_section()` and `attach_subtree()` only, the string `"ROOT"` is also a root shortcut; use `["ROOT"]` for a heading with that title. `remove_section()` returns a boolean, and `add_section()` returns the new node or `None` when the parent is missing.

## Copy sections between documents

```python
base = MarkdownTree()
base.parse("# Guide\nGuide text.\n")

appendix = MarkdownTree()
appendix.parse("# Extra\nMore text.\n\n## Details\nDetails here.\n")

# Copy every top-level section below Guide.
attached = base.attach_subtree("Guide", appendix)

# Or copy just one section, selected by path or node handle.
# attached = base.attach_subtree("Guide", appendix, ["Extra", "Details"])
```

Copies are independent of the source. Each copied root is placed one heading level below the target; differences in level within its subtree are preserved. Copying all sections copies the root's **children**, not source preamble text. Pass that text explicitly if the composed document needs it. Attaching a tree to itself is supported.

Markdown has only six heading levels. If a section cannot fit at the destination, `add_section()` or `attach_subtree()` raises `ValueError` rather than silently flattening it. Attachment validates all requested sections before changing the destination. `max_level` can set a stricter upper bound from 1 to 6. A multiline Setext title cannot in general be relevelled without changing its inline meaning; such an attachment raises `ValueError`.

At the lower level, `MarkdownNode.add_child()` moves a node, updates its parent, and rejects cycles and invalid heading levels; it does not relevel the node. `remove_child()` detaches it. `copy_with_level_delta()` rejects levels outside its allowed range instead of clamping them. Directly editing `children`, `parent`, or `level` can bypass these checks.

## Markdown behavior and validation

The parser recognizes top-level ATX and Setext headings. Heading-like text inside fenced or indented code, HTML blocks, block quotes, and lists remains section content. Markdown inside a container is not represented as a separate section tree. The scanner aims to follow CommonMark block rules when identifying headings; it does not render Markdown or enable GitHub-specific extensions such as tables. It is not certified as a complete CommonMark implementation, and unusual combinations of nested blocks may still expose edge cases.

A complete initial block starting with `---` and ending with `---` or `...` is treated as front matter and kept in the root content. This convention is ambiguous with ordinary Markdown. To disable this convention and scan the document without special front matter handling, use:

```python
tree.parse(markdown_text, front_matter=False)
```

`dump()` preserves original source for unchanged headings and content, and regenerates only edited parts. File decoding and newline handling are the caller's responsibility: for example, read with `open(path, encoding="utf-8", newline="")` if preserving file line endings matters.

By default, `dump()` validates the tree and, after edits, reparses the result to check that its section titles and levels still match the tree. This catches cases such as adding a heading after an unclosed code fence or adding heading syntax inside content. It raises `ValueError` if the hierarchy cannot be represented. `dump(validate=False)` skips this check when the caller explicitly prefers to handle that risk. Validation uses this same scanner, so it cannot detect a mistake shared by parsing and validation. It checks heading structure, not every aspect of rendered Markdown: moving content can change the meaning of reference links, HTML, or other context-dependent constructs.
