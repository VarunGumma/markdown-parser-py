<div align="center">

# markdown-parser-py

Turn raw Markdown into a manipulable heading tree, edit it programmatically, then emit valid Markdown again.

![status](https://img.shields.io/badge/status-experimental-orange)
![python](https://img.shields.io/badge/python-3.10+-blue)

</div>

## ✨ Features

- Parse Markdown into a hierarchical tree of headings (levels 1–6)
- Preserve and round‑trip section body content
- Query sections via simple dot paths (e.g. `Introduction.Installation.Windows`)
- Add / remove sections dynamically
- Attach (merge) whole subtrees across different Markdown documents with automatic heading level adjustment
- Dump back to Markdown or visualize structure in a `tree`-like ASCII output

## 📦 Installation

```bash
pip install markdown-parser-py
```

or, for an editable install

```bash
git clone https://github.com/VarunGumma/markdown-parser-py
cd markdown-parser-py
pip install -e ./
```

## 🧠 Core Concepts

The model is minimal:

```text
MarkdownTree
└── root (MarkdownNode level=0, title="ROOT")
	├── Child heading (level=1 => '#')
	│   └── Grandchild (level=2 => '##')
	└── ...
```

Each `MarkdownNode` stores:

- `level`: 0 for synthetic root; 1–6 for real headings
- `title`: heading text
- `content`: list of raw paragraph / code / list text blocks under that heading (excluding child headings)
- `children`: nested headings

## 🚀 Quick Start

```python
from markdown_parser.src import MarkdownTree

doc = """
# Intro
Some intro text.

## Install
Run `pip install x`.

## Usage
Basic usage here.

### CLI
Run `tool`.
"""

tree = MarkdownTree()
tree.parse(doc)

print('\n=== Visualize ===')
tree.visualize()

print('\n=== Dump Round Trip ===')
print(tree.dump())
```

Output (visualize):

```text
└── # Intro
	├── ## Install
	└── ## Usage
		└── ### CLI
```

## 🔍 Finding Sections

```python
node = tree.find_node_by_path('Intro.Install')  # '# Intro' > '## Install'
if node:
	print('Found:', node.title, 'level', node.level)
```

Dot paths walk downward by titles. A single component path refers to a top‑level heading (level 1). Returns `None` if not found.

## ➕ Adding Sections

```python
new = tree.add_section('Intro', 'Advanced', content='Deep dive coming soon.')
print('Added at level', new.level)
```

If `parent_path` is `""` or `"ROOT"`, the new section becomes a top‑level heading.

## ➖ Removing Sections

```python
tree.remove_section('Intro.Advanced')  # removes that subtree
```

## 🔗 Attaching / Merging Subtrees

You can merge content from another parsed Markdown document. Levels auto-adjust so the attached subtree root sits exactly one level below the chosen parent.

```python
from markdown_parser.src import MarkdownTree

base = MarkdownTree()
base.parse('# A\nIntro text.')

other = MarkdownTree()
other.parse('# Extra\nStuff here.\n\n## Deep\nDetails.')

# Attach ALL top-level sections from other under 'A'
base.attach_subtree('A', other)  # Equivalent to source_path=None

# Or attach only a specific subsection
# base.attach_subtree('A', other, source_path='Extra.Deep')

base.visualize()
print(base.dump())
```

If you attach the full tree (`source_path=None` / `'ROOT'`), each top-level section in the source is cloned with level adjusted: `new_level = parent.level + original_level`.

## 🧪 Advanced Example: Composing Documents

```python
def compose(product_readme: str, appendix_md: str) -> str:
	main_tree = MarkdownTree()
	main_tree.parse(product_readme)

	appendix_tree = MarkdownTree()
	appendix_tree.parse(appendix_md)

	# Ensure an Appendix section exists
	if not main_tree.find_node_by_path('Appendix'):
		main_tree.add_section('', 'Appendix')

	# Attach all appendix top-level sections under Appendix
	main_tree.attach_subtree('Appendix', appendix_tree)
	return main_tree.dump()
```

## 📝 Disclaimer

This is an early/experimental utility. Edge cases (nested fenced code blocks, Setext headings, ATX heading oddities, HTML blocks) are not fully supported yet.
