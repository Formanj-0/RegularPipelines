import textwrap

import regular_pipelines as rp


PIPELINE = textwrap.dedent("""\
    import sys
    import os
    import tempfile

    sys.path.append(os.path.join(os.getcwd(), '..'))
    import src as mp

    DATASET_PATH = 'placeholder'
    RESULTS_NAME = None
    USE_NAPARI = True
    THRESHOLD = 1

    tmp = tempfile.gettempdir()
    value = mp.double(THRESHOLD)
    with open(os.path.join(DATASET_PATH, 'out.txt'), 'w') as f:
        f.write(str(value))
""")


def make_host(tmp_path):
    functions = tmp_path / "host" / "src" / "functions"
    functions.mkdir(parents=True)
    (functions / "__init__.py").write_text("from .math_ops import double\n")
    (functions / "math_ops.py").write_text("def double(x):\n    return 2 * x\n")
    pipeline = tmp_path / "host" / "pipelines" / "pipe.py"
    pipeline.parent.mkdir()
    pipeline.write_text(PIPELINE)
    return pipeline, functions


def test_replace_parameters():
    text = "A = 1\nB = 'x'\n"
    out = rp.replace_parameters(text, {"A": [1, 2], "B": None})
    assert out == "A = [1, 2]\nB = None\n"


def test_prepare_script(tmp_path):
    pipeline, functions = make_host(tmp_path)
    dataset = tmp_path / "data1"
    dataset.mkdir()

    out = rp.prepare_script(pipeline, str(dataset), "res", {"THRESHOLD": 21}, functions)
    text = open(out).read()

    assert "def double" in text
    assert "import src as mp" not in text
    assert "mp." not in text
    assert "value = double(THRESHOLD)" in text
    assert "THRESHOLD = 21" in text
    assert "USE_NAPARI = False" in text
    assert "tmp = tempfile" in text  # word-boundary strip leaves tmp alone


def test_run_local(tmp_path):
    pipeline, functions = make_host(tmp_path)
    datasets = []
    for i in range(3):
        d = tmp_path / f"data{i}"
        d.mkdir()
        datasets.append(str(d))

    results = rp.local.run_scripts(
        pipeline, datasets, args={"THRESHOLD": 5},
        function_path=functions, num_runners=2, poll_interval=0.05,
    )

    assert all(r["success"] for r in results)
    for d in datasets:
        assert open(f"{d}/out.txt").read() == "10"
