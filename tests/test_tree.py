from markdown_parser import MarkdownTree


def test_parser():
    # GIVEN a Markdown document
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

    # WHEN parsing
    tree = MarkdownTree()
    tree.parse(doc)

    # THEN the correct structure is returned
    assert len(tree.root.children) == 1
    intro = tree.root.children[0]
    assert intro.title == "Intro"
    assert intro.content == ["Some intro text."]

    assert len(intro.children) == 2
    install = intro.children[0]
    assert install.title == "Install"
    assert install.content == ["Run `pip install x`."]
    usage = intro.children[1]
    assert usage.title == "Usage"
    assert usage.content == ["Basic usage here."]
    assert len(usage.children) == 1
    cli = usage.children[0]
    assert cli.title == "CLI"
    assert cli.content == ["Run `tool`."]
