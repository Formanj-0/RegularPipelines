from pathlib import Path
import re


def inline_mp_modules(
    source_script,
    output_script,
    functions_dir,
    alias="mp",
):
    """
    Prepend the source files corresponding to all mp.function(...)
    calls found in a script.

    Parameters
    ----------
    source_script : str or Path
        Original script.

    output_script : str or Path
        New script.

    functions_dir : str or Path
        Directory containing __init__.py and module files.

    alias : str, optional
        Name the host package is imported as in the script
        (``import src as mp`` -> ``"mp"``).
    """

    functions_dir = Path(functions_dir)

    script_text = Path(source_script).read_text()
    init_text = (functions_dir / "__init__.py").read_text()

    # ---------------------------------------------------------
    # Find all <alias>.function(...)
    # ---------------------------------------------------------

    called_functions = sorted(set(
        re.findall(rf"\b{re.escape(alias)}\.([A-Za-z_]\w*)\s*\(", script_text)
    ))

    print("Functions found:")
    print(called_functions)

    # ---------------------------------------------------------
    # Build function -> module lookup
    # ---------------------------------------------------------

    function_to_module = {}

    pattern = re.compile(
        r"from\s+\.(\w+)\s+import\s+(.+)"
    )

    for line in init_text.splitlines():

        m = pattern.match(line.strip())

        if not m:
            continue

        module = m.group(1)

        imported = [
            x.strip()
            for x in m.group(2).split(",")
        ]

        for func in imported:
            function_to_module[func] = module

    # ---------------------------------------------------------
    # Collect module text
    # ---------------------------------------------------------

    modules_added = set()
    prepend_text = []

    for func in called_functions:

        if func not in function_to_module:
            print(f"Warning: couldn't locate {func}")
            continue

        module = function_to_module[func]

        if module in modules_added:
            continue

        module_file = functions_dir / f"{module}.py"

        if not module_file.exists():
            print(f"Missing: {module_file}")
            continue

        prepend_text.append(
            f"\n# ===== BEGIN {module}.py =====\n"
        )

        prepend_text.append(module_file.read_text())

        prepend_text.append(
            f"\n# ===== END {module}.py =====\n"
        )

        modules_added.add(module)

    # ---------------------------------------------------------
    # Write output
    # ---------------------------------------------------------

    output = "\n".join(prepend_text) + "\n\n" + script_text

    Path(output_script).write_text(output)

    print(f"Saved -> {output_script}")
