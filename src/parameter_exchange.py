from pathlib import Path
import re


def parameter_exchange(
    source_script,
    output_script,
    replacements,
    strs_to_delete=None,
):
    """
    Copy a Python script, replace specified parameter values,
    and optionally delete arbitrary strings.

    Parameters
    ----------
    source_script : str or Path
        Original .py file.
    output_script : str or Path
        New file to write.
    replacements : dict
        Mapping like:
        {
            "PARAMETER1": "new value",
            "THRESHOLD": 0.75,
            "CHANNELS": [1, 2, 3]
        }

    strs_to_delete : list[str], optional
        List of literal strings to remove from the script.
    """

    text = Path(source_script).read_text()

    # Replace parameter values
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

    # Delete arbitrary strings
    if strs_to_delete:
        for s in strs_to_delete:
            text = text.replace(s, "")

    Path(output_script).write_text(text)