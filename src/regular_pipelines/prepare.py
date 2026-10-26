import os
import re

from .inline_mp_modules import inline_mp_modules
from .parameter_exchange import parameter_exchange

# Lines that only make sense when the pipeline runs from inside the host repo
DEFAULT_STRS_TO_DELETE = [
    "sys.path.append(os.path.join(os.getcwd(), '..'))",
]


def prepare_script(
    pipeline_path,
    dataset_path,
    results_name=None,
    args=None,
    function_path=None,
    alias="mp",
    strs_to_delete=None,
):
    """
    Build a standalone copy of a pipeline script inside a dataset folder.

    The host package's functions (``alias.func(...)``) are inlined from
    ``function_path``, the ``import ... as alias`` line is removed, the
    ``alias.`` prefixes are stripped, and ALL_CAPS parameters are replaced.

    Parameters
    ----------
    pipeline_path : str or Path
        Source pipeline script.
    dataset_path : str or Path
        Dataset folder; becomes ``DATASET_PATH`` in the script.
    results_name : str, optional
        Subfolder of ``dataset_path`` to write into; becomes ``RESULTS_NAME``.
    args : dict, optional
        Extra ``{PARAMETER: value}`` replacements.
    function_path : str or Path
        Host package's functions directory (contains ``__init__.py``).
    alias : str, optional
        Name the host package is imported as in the pipeline script.
    strs_to_delete : list[str], optional
        Literal strings to remove. Defaults to ``DEFAULT_STRS_TO_DELETE``.

    Returns
    -------
    str
        Path to the generated script.
    """

    if function_path is None:
        raise ValueError("function_path is required (the host package's functions directory)")

    if strs_to_delete is None:
        strs_to_delete = DEFAULT_STRS_TO_DELETE

    script_name = os.path.basename(pipeline_path)

    if results_name:
        destination_path = os.path.join(dataset_path, results_name, script_name)
    else:
        destination_path = os.path.join(dataset_path, script_name)

    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    inline_mp_modules(pipeline_path, destination_path, function_path, alias=alias)

    a = re.escape(alias)

    parameter_exchange(
        destination_path,
        destination_path,
        {
            "DATASET_PATH": dataset_path,
            "RESULTS_NAME": results_name,
            "USE_NAPARI": False,
            **(args or {}),
        },
        strs_to_delete=strs_to_delete,
        patterns_to_delete=[
            rf"^[ \t]*import\s+[\w.]+\s+as\s+{a}[ \t]*$",  # import src as mp
            rf"\b{a}\.",                                    # mp.func -> func
        ],
    )

    return destination_path
