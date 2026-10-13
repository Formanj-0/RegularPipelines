import sys
import os
import subprocess
import time

def run_script(
    pipeline_path,
    dataset_path,
    results_name: str = None,
    args=None,
    function_path: str = None,
        ):
    if args is None:
        args = {}

    script_name = os.path.basename(pipeline_path)

    if results_name:
        destination_path = os.path.join(dataset_path, results_name, script_name)
    else:
        destination_path = os.path.join(dataset_path, script_name)

    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    strs_to_delete = [
        "sys.path.append(os.path.join(os.getcwd(), '..'))",
        "import src as mp",
        "mp.",
    ]

    mp.inline_mp_modules(
        pipeline_path,
        destination_path,
        function_path,
    )

    mp.parameter_exchange(
        destination_path,
        destination_path,
        {"DATASET_PATH": dataset_path, 'RESULTS_NAME': results_name, 'USE_NAPARI': False, **args},
        strs_to_delete,
    )

    # Create a log file alongside the generated script
    log_path = os.path.splitext(destination_path)[0] + ".log"

    log_file = open(log_path, "w", buffering=1)  # line buffered

    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"   # optional but recommended

    process = subprocess.Popen(
        [sys.executable, destination_path],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    return {
        "script": script_name,
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
):
    """
    Run the same pipeline on multiple datasets with at most
    `num_runners` concurrent Python processes.
    """

    if args is None:
        args = {}

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

            # Process finished
            stdout, stderr = process.communicate()

            runtime = time.time() - job["start_time"]
            success = process.returncode == 0

            result = {
                "dataset": job["dataset"],
                "script": job["script"],
                "success": success,
                "returncode": process.returncode,
                "runtime": runtime,
                "stdout": stdout,
                "stderr": stderr,
            }

            results.append(result)

            if success:
                print(f"✓ {job['dataset']} ({runtime:.1f}s)")
            else:
                print(f"✗ {job['dataset']} ({runtime:.1f}s)")
                print(stderr)

            running.remove(job)

            # Launch the next waiting job immediately
            if pending:
                launch(pending.pop(0))

        time.sleep(poll_interval)

    # ---------- Summary ----------
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    successes = 0

    for r in results:
        status = "PASS" if r["success"] else "FAIL"

        print(
            f"{status:4} | "
            f"{r['runtime']:6.1f}s | "
            f"{r['dataset']}"
        )

        successes += r["success"]

    print("-" * 80)
    print(f"{successes}/{len(results)} jobs completed successfully.")

    return results