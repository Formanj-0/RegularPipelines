"""Reusable tooling for turning pipeline scripts into standalone jobs.

Typical use from a host project::

    import regular_pipelines as rp

    rp.local.run_scripts(pipeline_path, dataset_paths, function_path=...)
    batch = rp.slurm.run_scripts(pipeline_path, dataset_paths, function_path=...)
"""

from .parameter_exchange import parameter_exchange, replace_parameters
from .inline_mp_modules import inline_mp_modules
from .build_script import build_script
from .prepare import prepare_script
from . import run_local as local
from . import run_slurm as slurm

__version__ = "0.1.0"

__all__ = [
    "parameter_exchange",
    "replace_parameters",
    "inline_mp_modules",
    "build_script",
    "prepare_script",
    "local",
    "slurm",
]
