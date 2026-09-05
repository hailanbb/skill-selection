from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import is_within, local_timestamp, write_json
from run_workspace import validate_workspace


SAFE_METADATA_KEYS = (
    "id",
    "title",
    "description",
    "uploader",
    "uploader_id",
    "channel",
    "channel_id",
    "timestamp",
    "release_timestamp",
    "upload_date",
    "release_date",
    "duration",
    "duration_string",
    "view_count",
    "like_count",
    "comment_count",
    "repost_count",
    "tags",
    "categories",
    "webpage_url",
    "extractor",
    "extractor_key",
)


def resolve_yt_dlp(explicit: str | None) -> str:
    if explicit:
        return explicit
    executable = shutil.which("yt-dlp")
    if executable:
        return executable
    raise FileNotFoundError("yt-dlp was not found on PATH; install it or pass --yt-dlp <executable>")


def build_yt_dlp_command(executable: str, source_url: str) -> list[str]:
    return [
        executable,
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--",
        source_url,
    ]


def child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def safe_metadata(raw: dict[str, Any], source_url: str) -> dict[str, Any]:
    metadata = {key: raw[key] for key in SAFE_METADATA_KEYS if key in raw}
    metadata["source_url"] = source_url
    metadata["extracted_at"] = local_timestamp()
    return metadata


def extract_metadata(source_url: str, output_path: Path, yt_dlp: str | None) -> dict[str, Any]:
    executable = resolve_yt_dlp(yt_dlp)
    command = build_yt_dlp_command(executable, source_url)
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env=child_environment(),
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"yt-dlp exited with code {completed.returncode}"
        raise RuntimeError(detail)
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"yt-dlp returned invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("yt-dlp metadata root must be an object")
    metadata = safe_metadata(raw, source_url)
    write_json(output_path.expanduser().resolve(), metadata)
    return metadata


def background_command(
    source_url: str,
    output_path: Path,
    status_path: Path,
    yt_dlp: str | None,
    run_dir: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--url",
        source_url,
        "--output",
        str(output_path),
        "--status-file",
        str(status_path),
        "--run-dir",
        str(run_dir),
        "--worker",
    ]
    if yt_dlp:
        command.extend(["--yt-dlp", yt_dlp])
    return command


def start_background(
    source_url: str,
    output_path: Path,
    status_path: Path,
    log_path: Path,
    yt_dlp: str | None,
    run_dir: Path,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = background_command(source_url, output_path, status_path, yt_dlp, run_dir)
    popen_options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
        "shell": False,
        "env": child_environment(),
    }
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_options["start_new_session"] = True
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(command, stdout=log_file, **popen_options)
    return process.pid


def status_payload(state: str, output_path: Path, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "output": str(output_path),
        "updated_at": local_timestamp(),
    }
    payload.update(extra)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract safe Douyin yt-dlp metadata without nested PowerShell command strings"
    )
    parser.add_argument("--url", required=True, help="Source video or share URL")
    parser.add_argument("--output", type=Path, required=True, help="UTF-8 JSON output path")
    parser.add_argument("--run-dir", type=Path, required=True, help="Marked workspace for all output/status/log files")
    parser.add_argument("--yt-dlp", help="Optional yt-dlp executable path")
    parser.add_argument("--background", action="store_true", help="Run extraction in a detached child process")
    parser.add_argument("--status-file", type=Path, help="Background job status JSON path")
    parser.add_argument("--log-file", type=Path, help="Background job log path")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    validate_workspace(run_dir)
    output_path = args.output.expanduser().resolve()
    status_path = (
        args.status_file.expanduser().resolve()
        if args.status_file
        else output_path.with_suffix(output_path.suffix + ".status.json")
    )

    if args.background and args.worker:
        parser.error("--background and --worker cannot be used together")
    checked_paths = [output_path, status_path]

    if args.background:
        log_path = (
            args.log_file.expanduser().resolve()
            if args.log_file
            else output_path.with_suffix(output_path.suffix + ".log")
        )
        checked_paths.append(log_path)
        if any(not is_within(path, run_dir) for path in checked_paths):
            raise SystemExit("Metadata output, status, and log must stay inside the marked run workspace")
        write_json(status_path, status_payload("starting", output_path))
        try:
            pid = start_background(args.url, output_path, status_path, log_path, args.yt_dlp, run_dir)
        except OSError as exc:
            write_json(status_path, status_payload("failed", output_path, error=str(exc)))
            print(str(exc), file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "started": True,
                    "pid": pid,
                    "output": str(output_path),
                    "status_file": str(status_path),
                    "log_file": str(log_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if any(not is_within(path, run_dir) for path in checked_paths):
        raise SystemExit("Metadata output and status must stay inside the marked run workspace")

    if args.worker:
        write_json(status_path, status_payload("running", output_path, pid=os.getpid()))
    try:
        metadata = extract_metadata(args.url, output_path, args.yt_dlp)
    except (FileNotFoundError, OSError, RuntimeError, UnicodeError, ValueError) as exc:
        if args.worker:
            write_json(status_path, status_payload("failed", output_path, error=str(exc)))
        print(str(exc), file=sys.stderr)
        return 2
    if args.worker:
        write_json(status_path, status_payload("succeeded", output_path, pid=os.getpid()))
    print(
        json.dumps(
            {
                "extracted": True,
                "output": str(output_path),
                "id": metadata.get("id", ""),
                "title": metadata.get("title", ""),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
