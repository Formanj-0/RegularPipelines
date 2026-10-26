from pathlib import Path
import re


def replace_parameters(text, replacements):
    """
    Replace top-level ``NAME = value`` assignments in source text.

    Each value is written with ``repr`` so strings, numbers, lists,
    None, etc. round-trip as Python literals.

    Returns the new text.
    """

    for param, value in replacements.items():

        pattern = rf"^(\s*{re.escape(param)}\s*=\s*).*$"

        text, count = re.subn(
            pattern,
            lambda m: m.group(1) + repr(value),
            text,
            flags=re.MULTILINE,
        )

        if count == 0:
            print(f"Warning: {param} not found")

    return text


def parameter_exchange(
    source_script,
    output_script,
    replacements,
    strs_to_delete=None,
    patterns_to_delete=None,
):
    """
    Copy a Python script, replace specified parameter values,
    and optionally delete arbitrary strings.

    Parameters
    ----------
    source_script : str or Path
        Original .py file.
    output_script : str or Path
        New file to write. May be the same as ``source_script``.
    replacements : dict
        Mapping like:
        {
            "PARAMETER1": "new value",
            "THRESHOLD": 0.75,
            "CHANNELS": [1, 2, 3]
        }

    strs_to_delete : list[str], optional
        List of literal strings to remove from the script.

    patterns_to_delete : list[str], optional
        List of regular expressions (multiline mode) to remove.
    """

    text = Path(source_script).read_text()

    text = replace_parameters(text, replacements)

    if strs_to_delete:
        for s in strs_to_delete:
            text = text.replace(s, "")

    if patterns_to_delete:
        for p in patterns_to_delete:
            text = re.sub(p, "", text, flags=re.MULTILINE)

    Path(output_script).write_text(text)
