"""Demo-local artefacts and catalogue task helpers."""

from __future__ import annotations

import json
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any

from django.utils import timezone

PULSE_DELAY_SECONDS = 8
SUMMARISE_DELAY_SECONDS = 15
PROBE_SAMPLE_THRESHOLD = 3
PROBE_MAX_ATTEMPTS = 3
PROBE_MAX_DELAY_SECONDS = 8


def _var_dir() -> Path:
    return VAR_DIR


VAR_DIR = Path(__file__).resolve().parent.parent / "var"
SAMPLES_NAME = "samples.jsonl"
REPORT_NAME = "report.json"
STOP_NAME = "pulse.stop"
ACTIVE_NAME = "pulse.active"


def samples_path() -> Path:
    return _var_dir() / SAMPLES_NAME


def report_path() -> Path:
    return _var_dir() / REPORT_NAME


def stop_path() -> Path:
    return _var_dir() / STOP_NAME


def active_path() -> Path:
    return _var_dir() / ACTIVE_NAME


def ensure_var_dir() -> Path:
    path = _var_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def pulse_stopped() -> bool:
    return stop_path().is_file()


def pulse_running() -> bool:
    return active_path().is_file()


def request_pulse_stop() -> None:
    ensure_var_dir()
    stop_path().write_text("stop\n", encoding="utf-8")
    clear_pulse_running()


def clear_pulse_stop() -> None:
    path = stop_path()
    if path.is_file():
        path.unlink()


def mark_pulse_running() -> None:
    ensure_var_dir()
    active_path().write_text("running\n", encoding="utf-8")


def clear_pulse_running() -> None:
    path = active_path()
    if path.is_file():
        path.unlink()


def _dir_bytes() -> int:
    root = ensure_var_dir()
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _read_samples() -> list[dict[str, Any]]:
    path = samples_path()
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and not text.endswith("\n"):
        lines = lines[:-1]
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _atomic_write_text(path: Path, text: str) -> None:
    ensure_var_dir()
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def run_pulse(*, generation: int = 1) -> dict[str, Any]:
    ensure_var_dir()
    sample = {
        "generation": generation,
        "at": timezone.now().isoformat(),
        "dir_bytes": _dir_bytes(),
    }
    with samples_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample) + "\n")
    sample["sample_count"] = len(_read_samples())
    sample["reschedule"] = not pulse_stopped()
    return sample


def run_summarise() -> dict[str, Any]:
    samples = _read_samples()
    sizes = [int(row["dir_bytes"]) for row in samples if "dir_bytes" in row]
    report = {
        "count": len(samples),
        "dir_bytes_min": min(sizes) if sizes else 0,
        "dir_bytes_max": max(sizes) if sizes else 0,
        "dir_bytes_mean": statistics.fmean(sizes) if sizes else 0.0,
        "at": timezone.now().isoformat(),
    }
    _atomic_write_text(report_path(), json.dumps(report, indent=2) + "\n")
    report["report"] = str(report_path())
    return report


def probe_retry_delay(attempt: int) -> int:
    return min(2**attempt, PROBE_MAX_DELAY_SECONDS)


def run_probe(*, attempt: int = 1) -> dict[str, Any]:
    samples = _read_samples()
    result: dict[str, Any] = {
        "ok": len(samples) >= PROBE_SAMPLE_THRESHOLD,
        "attempt": attempt,
        "samples": len(samples),
    }
    if not result["ok"] and attempt < PROBE_MAX_ATTEMPTS:
        result["retry_in"] = probe_retry_delay(attempt)
    return result


def recent_samples(limit: int = 20) -> list[dict[str, Any]]:
    return _read_samples()[-limit:]
