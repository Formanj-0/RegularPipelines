from pathlib import Path
import ast

from .parameter_exchange import replace_parameters


class CallVisitor(ast.NodeVisitor):
    """Collect function names that are called."""

    def __init__(self):
        self.calls = set()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.calls.add(node.func.id)
        self.generic_visit(node)


def called_functions(func_node):
    visitor = CallVisitor()
    visitor.visit(func_node)
    return visitor.calls


def parse_source(source_file):
    text = Path(source_file).read_text()
    tree = ast.parse(text)

    functions = {}
    imports = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)

    return text, tree, functions, imports


def gather_dependencies(start_functions, function_defs):
    """
    Recursively gather all function dependencies.
    """
    needed = set()

    def recurse(name):
        if name in needed:
            return

        if name not in function_defs:
            return

        needed.add(name)

        for dep in called_functions(function_defs[name]):
            recurse(dep)

    for fn in start_functions:
        recurse(fn)

    return needed


def build_header(imports, function_defs, needed_functions):
    pieces = []

    for node in imports:
        pieces.append(ast.unparse(node))

    if imports:
        pieces.append("")

    # preserve original order
    ordered = [
        node.name
        for node in function_defs.values()
        if node.name in needed_functions
    ]

    for name in ordered:
        pieces.append(ast.unparse(function_defs[name]))
        pieces.append("")

    return "\n".join(pieces).rstrip()


def build_script(
    source_script,
    output_script,
    replacements,
    inline_functions=None,
):
    """
    Export a standalone script.

    Parameters
    ----------
    source_script : str or Path

    output_script : str or Path

    replacements : dict
        ALL_CAPS variables to replace.

    inline_functions : list[str], optional
        Functions to prepend to the script. Their dependencies are
        automatically included.
    """

    text, _, function_defs, imports = parse_source(source_script)

    ############################################################
    # Replace parameters
    ############################################################

    text = replace_parameters(text, replacements)

    ############################################################
    # Inline functions
    ############################################################

    if inline_functions:

        needed = gather_dependencies(
            inline_functions,
            function_defs,
        )

        header = build_header(
            imports,
            function_defs,
            needed,
        )

        text = header + "\n\n" + text

    Path(output_script).write_text(text)

    print(f"Wrote {output_script}")
