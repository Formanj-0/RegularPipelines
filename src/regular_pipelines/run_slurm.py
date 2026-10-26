import os
import re
import subprocess
import threading
import time
from collections import deque

from .prepare import prepare_script

# Resolved against the cwd at submit time (not import time)
SLURM_OUTPUT_DIR = "slurm_output"

ACTIVE_STATES = {
    "PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "SUSPENDED",
    "REQUEUED", "REQUEUE_HOLD", "REQUEUE_FED", "RESIZING", "SIGNALING",
    "STAGE_OUT", "STOPPED", "RESV_DEL_HOLD",
}


def _run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def get_slurm_states(job_ids):
    """Return {job_id: state}. Jobs SLURM doesn't report yet are left out."""
    job_ids = [str(j) for j in job_ids]
    if not job_ids:
        return {}

    states = {}

    # One squeue call for all jobs instead of one per job
    try:
        r = _run(["squeue", "-h", "-j", ",".join(job_ids), "-o", "%i %T"])
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                states[parts[0]] = parts[1]
    except subprocess.TimeoutExpired:
        pass

    # Jobs no longer in the queue: check accounting
    missing = [j for j in job_ids if j not in states]
    if missing:
        try:
            r = _run(["sacct", "-n", "-X", "-P", "-j", ",".join(missing), "-o", "JobID,State"])
            for line in r.stdout.splitlines():
                job_id, _, state = line.partition("|")
                if state:
                    # "CANCELLED by 1234" -> "CANCELLED"
                    states[job_id.strip()] = state.split()[0]
        except subprocess.TimeoutExpired:
            pass

    return states


def get_slurm_state(job_id):
    return get_slurm_states([job_id]).get(str(job_id), "")


def _check_line_endings(path):
    with open(path, "rb") as f:
        if b"\r\n" in f.read():
            raise RuntimeError(
                f"{path} has Windows (CRLF) line endings and sbatch will reject it.\n"
                f"Fix with: dos2unix {path}"
            )


def _tail(path, n=20):
    try:
        with open(path, errors="replace") as f:
            return "".join(deque(f, maxlen=n))
    except OSError:
        return None


def _exit_status_from_log(path):
    """Fallback when sacct has no record: read the 'Exit status: N' line the runner prints."""
    try:
        with open(path, errors="replace") as f:
            codes = re.findall(r"^Exit status: (\d+)", f.read(), re.M)
        return int(codes[-1]) if codes else None
    except (OSError, TypeError):
        return None


def run_script(
    pipeline_path,
    dataset_path,
    results_name: str = None,
    args=None,
    function_path: str = None,
    slurm_script="python_runner.sh",
    output_dir=SLURM_OUTPUT_DIR,
    alias="mp",
):
    """Build the standalone script for one dataset and submit it with sbatch."""

    script_name = os.path.basename(pipeline_path)

    destination_path = prepare_script(
        pipeline_path,
        dataset_path,
        results_name=results_name,
        args=args,
        function_path=function_path,
        alias=alias,
    )

    # ---------------------------------------------------------
    # Submit to SLURM
    # ---------------------------------------------------------

    slurm_script = os.path.abspath(slurm_script)
    if not os.path.isfile(slurm_script):
        raise FileNotFoundError(f"SLURM script not found: {slurm_script}")
    _check_line_endings(slurm_script)

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    dataset_name = os.path.basename(os.path.normpath(dataset_path))
    job_name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{os.path.splitext(script_name)[0]}_{dataset_name}")
    log_pattern = os.path.join(output_dir, f"{job_name}_%j.log")

    # --output on the command line overrides the #SBATCH line in the script
    result = _run([
        "sbatch",
        "--parsable",
        f"--job-name={job_name}",
        f"--output={log_pattern}",
        slurm_script,
        destination_path,
    ])

    if result.returncode != 0:
        raise RuntimeError(f"sbatch failed ({result.returncode}):\n{result.stderr.strip()}")

    # --parsable prints "jobid" or "jobid;cluster"
    job_id = result.stdout.strip().split(";")[0]
    log_path = log_pattern.replace("%j", job_id)

    print(f"Submitted {script_name} for {dataset_name} (SLURM {job_id})")

    return {
        "script": script_name,
        "path": destination_path,
        "dataset": dataset_path,
        "job_id": job_id,
        "log": log_path,
    }


class SlurmBatch:
    """Runs a queue of SLURM jobs in a background thread so the notebook stays usable."""

    def __init__(self, dataset_paths, num_runners, poll_interval, lost_after, submit_kwargs):
        self.num_runners = num_runners
        self.poll_interval = poll_interval
        self.lost_after = lost_after
        self._submit_kwargs = submit_kwargs

        self.pending = deque(dataset_paths)
        self.running = []
        self.results = []
        self.error = None

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ---------------------------------------------------------
    # Background loop
    # ---------------------------------------------------------

    def _loop(self):
        try:
            while not self._stop.is_set() and (self.pending or self.running):
                self._fill()
                self._check()
                self._stop.wait(self.poll_interval)
        except Exception as e:
            self.error = e
            print(f"SlurmBatch monitor crashed: {e!r}")
        finally:
            if not self._stop.is_set():
                self.summary()

    def _fill(self):
        while not self._stop.is_set():
            with self._lock:
                if not self.pending or len(self.running) >= self.num_runners:
                    return
                dataset = self.pending.popleft()

            try:
                job = run_script(dataset_path=dataset, **self._submit_kwargs)
            except Exception as e:
                print(f"✗ {dataset} (submission failed: {e})")
                with self._lock:
                    self.results.append({
                        "dataset": dataset,
                        "script": os.path.basename(self._submit_kwargs["pipeline_path"]),
                        "job_id": None,
                        "success": False,
                        "state": "SUBMIT_FAILED",
                        "runtime": 0.0,
                        "log": None,
                        "error": str(e),
                    })
                continue

            job.update(submit_time=time.time(), seen=False, state="SUBMITTED")
            with self._lock:
                self.running.append(job)

    def _check(self):
        with self._lock:
            jobs = list(self.running)
        if not jobs:
            return

        states = get_slurm_states(j["job_id"] for j in jobs)

        for job in jobs:
            state = states.get(job["job_id"])

            if state in ACTIVE_STATES:
                job["seen"] = True
                job["state"] = state
                continue

            if state is None:
                # Either just submitted and not visible yet, or no accounting record
                if not job["seen"] and time.time() - job["submit_time"] < self.lost_after:
                    continue
                code = _exit_status_from_log(job["log"])
                state = {None: "UNKNOWN", 0: "COMPLETED"}.get(code, "FAILED")

            self._finish(job, state)

    def _finish(self, job, state):
        runtime = time.time() - job["submit_time"]
        success = state == "COMPLETED"

        with self._lock:
            self.results.append({
                "dataset": job["dataset"],
                "script": job["script"],
                "job_id": job["job_id"],
                "success": success,
                "state": state,
                "runtime": runtime,
                "log": job["log"],
            })
            self.running.remove(job)

        if success:
            print(f"✓ {job['dataset']} (SLURM {job['job_id']}, {runtime:.1f}s)")
        else:
            print(f"✗ {job['dataset']} (SLURM {job['job_id']}, state={state})")
            print(f"  log: {job['log']}")
            tail = _tail(job["log"])
            if tail:
                print("  " + tail.rstrip().replace("\n", "\n  "))

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    @property
    def done(self):
        return not self._thread.is_alive()

    def wait(self, timeout=None):
        """Block until everything finishes (only if you want to)."""
        self._thread.join(timeout)
        return self.results

    def cancel(self):
        """Stop launching new jobs and scancel the running ones."""
        self._stop.set()
        with self._lock:
            ids = [j["job_id"] for j in self.running]
            self.pending.clear()
        if ids:
            _run(["scancel", *ids])
        print(f"Cancelled {len(ids)} running job(s); pending queue cleared.")

    def status(self):
        print(repr(self))
        with self._lock:
            for j in self.running:
                elapsed = time.time() - j["submit_time"]
                print(f"  {j['state']:11} | {elapsed:7.1f}s | SLURM {j['job_id']} | {j['dataset']}")

    def summary(self):
        with self._lock:
            results = list(self.results)

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        for r in results:
            status = "PASS" if r["success"] else "FAIL"
            print(
                f"{status:4} | {r['runtime']:7.1f}s | {r['state']:13} | "
                f"SLURM {r['job_id'] or '-':>8} | {r['dataset']}"
            )
        print("-" * 80)
        print(f"{sum(r['success'] for r in results)}/{len(results)} jobs completed successfully.")

    def __repr__(self):
        with self._lock:
            n_done = len(self.results)
            n_ok = sum(r["success"] for r in self.results)
            n_run, n_pend = len(self.running), len(self.pending)
        state = "finished" if self.done else "running"
        return f"<SlurmBatch {state}: {n_ok}/{n_done} succeeded, {n_run} running, {n_pend} pending>"


def run_scripts(
    pipeline_path,
    dataset_paths,
    results_name=None,
    args=None,
    function_path=None,
    num_runners=20,
    poll_interval=5,
    slurm_script="python_runner.sh",
    output_dir=SLURM_OUTPUT_DIR,
    lost_after=300,
    alias="mp",
):
    """
    Start the jobs and return immediately. Returns a SlurmBatch handle:

        batch             # one-line progress
        batch.status()    # what's running and in which state
        batch.results     # finished jobs so far
        batch.cancel()    # scancel everything still running
        batch.wait()      # block until done
    """
    return SlurmBatch(
        dataset_paths=list(dataset_paths),
        num_runners=num_runners,
        poll_interval=poll_interval,
        lost_after=lost_after,
        submit_kwargs=dict(
            pipeline_path=pipeline_path,
            results_name=results_name,
            args=args or {},
            function_path=function_path,
            slurm_script=slurm_script,
            output_dir=output_dir,
            alias=alias,
        ),
    )
