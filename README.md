# RegularPipelines

Reusable tooling for research pipelines: write a pipeline once as a normal
script that calls your project's helper functions (`mp.some_function(...)`),
then turn it into a **standalone script per dataset** and run it locally or on
SLURM.

For each dataset the runner:

1. copies the pipeline into `<dataset>/<results_name>/`,
2. inlines the source of every helper module the script calls (`mp.func(...)`),
3. removes the `import ... as mp` line and the `mp.` prefixes,
4. replaces ALL_CAPS parameters (`DATASET_PATH`, `RESULTS_NAME`, `USE_NAPARI`, plus your `args`),
5. runs it (local subprocess or `sbatch`) and logs the output.

The generated script has no dependency on your repo, so it is a frozen,
reproducible record of exactly what ran on that dataset.

## Adding it to a project

As a git submodule (recommended, so each project pins a version):

```bash
git submodule add https://github.com/Formanj-0/RegularPipelines.git RegularPipelines
```

```bash
pip install -e RegularPipelines
```

Or without a submodule:

```bash
pip install git+https://github.com/Formanj-0/RegularPipelines.git
```

Requires Python 3.9+; no third-party dependencies.

## Host project layout

The package expects your project to look roughly like this:

```
MyProject/
├── src/
│   ├── __init__.py          # from .functions import *
│   └── functions/
│       ├── __init__.py      # from .compute_mask import compute_mask   (one per line)
│       └── compute_mask.py
├── pipelines/
│   └── my_pipeline.py
└── python_runner.sh         # only for SLURM
```

A pipeline script:

```python
import sys, os
sys.path.append(os.path.join(os.getcwd(), '..'))
import src as mp

DATASET_PATH = r'path/used/while/developing'
RESULTS_NAME = None
USE_NAPARI = True
THRESHOLD = 100

mask = mp.compute_mask(DATASET_PATH, THRESHOLD)
```

Only modules listed as `from .module import name` in `functions/__init__.py`
are inlined, so keep each helper module self-contained (no relative imports
between helper modules).

## Running

```python
import regular_pipelines as rp

# Local: blocks until done, at most num_runners processes at once
results = rp.local.run_scripts(
    pipeline_path="pipelines/my_pipeline.py",
    dataset_paths=["data/ds1", "data/ds2"],
    results_name="threshold_100",
    args={"THRESHOLD": 100},
    function_path="src/functions",
    num_runners=4,
)

# SLURM: returns immediately with a handle
batch = rp.slurm.run_scripts(
    pipeline_path="pipelines/my_pipeline.py",
    dataset_paths=dataset_paths,
    results_name="threshold_100",
    args={"THRESHOLD": 100},
    function_path="src/functions",
    slurm_script="python_runner.sh",   # gets the generated script path as $1
)
batch            # progress summary
batch.status()   # running jobs and their SLURM state
batch.cancel()   # scancel everything
batch.wait()     # block until finished
```

If your scripts import the host package under a different name, pass
`alias=` (e.g. `alias="cf"` for `import clownfish as cf`).

Lower-level building blocks are also exported: `prepare_script`,
`inline_mp_modules`, `parameter_exchange`, `replace_parameters`,
`build_script`.

## Development

```bash
pip install -e ".[test]"
```

```bash
pytest
```
