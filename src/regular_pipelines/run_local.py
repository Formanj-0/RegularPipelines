import os
import subprocess
import sys
import time
from collections import deque

from .prepare import prepare_script


def _tail(path, n=20):
    try:
        with open(path, errors="replace") as f:
            return "".join(deque(f, maxlen=n))
    except OSError:
        return None


def run_script(
    pipeline_path,
    dataset_path,
    results_name: str = None,
    args=None,
    function_path: str = None,
    alias="mp",
):
    """Build the standalone script for one dataset and start it in a subprocess."""

    destination_path = prepare_script(
        pipeline_path,
        dataset_path,
        results_name=results_name,
        args=args,
        function_path=function_path,
        alias=alias,
    )

    # Create a log file alongside the generated script
    log_path = os.path.splitext(destination_path)[0] + ".log"

    log_file = open(log_path, "w", buffering=1)  # line buffered

    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"   # no GUI windows from background jobs

    process = subprocess.Popen(
        [sys.executable, "-u", destination_path],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    return {
        "script": os.path.basename(pipeline_path),
        "path": destination_path,
        "log_path": log_path,
        "log_file": log_file,
        "process": process,
    }


def run_scripts(
    pipeline_path,
    dataset_paths,
    results_name=None,
    args=None,
    function_path=None,
    num_runners=4,
    poll_interval=0.25,
    alias="mp",
):
    """
    Run the same pipeline on multiple datasets with at most
    `num_runners` concurrent Python processes.
    """

    pending = list(dataset_paths)
    running = []
    results = []

    def launch(dataset_path):
        job = run_script(
            pipeline_path=pipeline_path,
            dataset_path=dataset_path,
            results_name=results_name,
            args=args,
            function_path=function_path,
            alias=alias,
        )

        job["dataset"] = dataset_path
        job["start_time"] = time.time()

        running.append(job)

        print(f"Started: {dataset_path}")

    # Fill the initial worker pool
    while pending and len(running) < num_runners:
        launch(pending.pop(0))

    # Continue until everything has completed
    while running:

        # Iterate over a copy since we may remove items
        for job in running[:]:

            process = job["process"]

            if process.poll() is None:
                continue

            job["log_file"].close()

            runtime = time.time() - job["start_time"]
            success = process.returncode == 0

            results.append({
                "dataset": job["dataset"],
                "script": job["script"],
                "success": success,
                "returncode": process.returncode,
                "runtime": runtime,
                "log": job["log_path"],
            })

            if success:
                print(f"✓ {job['dataset']} ({runtime:.1f}s)")
            else:
                print(f"✗ {job['dataset']} ({runtime:.1f}s)")
                print(f"  log: {job['log_path']}")
                tail = _tail(job["log_path"])
                if tail:
                    print("  " + tail.rstrip().replace("\n", "\n  "))

            running.remove(job)

            # Launch the next waiting job immediately
            if pending:
                launch(pending.pop(0))

        time.sleep(poll_interval)

    # ---------- Summary ----------
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(f"{status:4} | {r['runtime']:6.1f}s | {r['dataset']}")

    print("-" * 80)
    print(f"{sum(r['success'] for r in results)}/{len(results)} jobs completed successfully.")

    return results
