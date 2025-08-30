class MarkdownNode:
    def __init__(self, level, title, parent=None):
        self.level = level  # Heading level (0=root, 1=#, etc.)
        self.title = title  # Heading text
        self.content = []  # List of raw markdown strings (any content)
        self.children = []  # List of child MarkdownNode(s)
        self.parent = parent  # Parent node reference

    def add_child(self, node):
        self.children.append(node)
        node.parent = self

    def add_content(self, text):
        if text.strip():
            self.content.append(text.rstrip())

    def remove_child(self, node):
        self.children.remove(node)

    def dump(self) -> str:
        """Generate full markdown string from node tree recursively."""
        lines = []
        if self.level > 0:
            lines.append("#" * self.level + " " + self.title)
        if self.content:
            lines.append("\n".join(self.content))
        for child in self.children:
            lines.append(child.dump())
        return "\n\n".join(lines)

    def print_tree(self, indent="", last=True):
        """Print a tree-like structure of headings similar to Linux `tree` command."""
        prefix = indent + ("└── " if last else "├── ")
        if self.level > 0:
            print(prefix + f"{'#' * self.level} {self.title}")
        for i, child in enumerate(self.children):
            next_indent = indent + ("    " if last else "│   ")
            child.print_tree(next_indent, i == len(self.children) - 1)

    def copy_with_level_delta(self, delta: int, max_level: int = 6):
        """Deep copy this subtree adjusting heading levels by delta (clamped)."""
        if self.level == 0:
            new_level = 0
        else:
            new_level = self.level + delta
            if new_level < 1:
                new_level = 1
            if new_level > max_level:
                new_level = max_level
        clone = MarkdownNode(new_level, self.title)
        clone.content = list(self.content)
        for child in self.children:
            clone.add_child(child.copy_with_level_delta(delta, max_level))
        return clone
