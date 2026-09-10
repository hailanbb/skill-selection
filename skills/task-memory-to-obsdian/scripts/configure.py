"""Shared local path configuration; no AI-provider state or note mutation."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from save_notes import Invalid, relative, reject_links


def config_path(explicit=None):
    value = explicit or os.environ.get("TASK_MEMORY_CONFIG")
    path = Path(value).expanduser() if value else Path.home() / ".config" / "task-memory-to-obsdian" / "config.json"
    if not path.is_absolute():
        raise Invalid("Config path must be absolute")
    reject_links(path)
    return path


def validate(config):
    if not isinstance(config, dict) or set(config) != {"schema_version", "vault_root", "archive_root"} or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise Invalid("Unsupported configuration schema")
    if not isinstance(config["vault_root"], str):
        raise Invalid("Invalid vault root")
    vault = Path(config["vault_root"])
    if not vault.is_absolute() or not vault.is_dir():
        raise Invalid("Configured vault is missing or not an absolute directory")
    reject_links(vault)
    archive = vault / relative(config["archive_root"])
    reject_links(archive)
    if archive.exists() and not archive.is_dir():
        raise Invalid("Archive destination is a file")
    return config


def load(explicit=None):
    path = config_path(explicit)
    if not path.is_file():
        raise Invalid("No local configuration; ask the user for an archive destination first")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def describe(explicit=None):
    path = config_path(explicit)
    if not path.exists():
        return {"needs_setup": True, "config_path": str(path)}
    try:
        return {"needs_setup": False, "config_path": str(path), **load(explicit)}
    except (OSError, ValueError, TypeError) as error:
        return {"needs_setup": True, "config_path": str(path), "error": str(error)}


def build(destination, vault_root=None):
    target = Path(destination).expanduser()
    if not target.is_absolute():
        raise Invalid("Ask for an absolute archive destination")
    reject_links(target)
    if target.exists() and not target.is_dir():
        raise Invalid("Archive destination is a file")
    if vault_root:
        vault = Path(vault_root).expanduser()
        if not vault.is_absolute() or not vault.is_dir():
            raise Invalid("The explicitly selected vault must already exist")
        reject_links(vault)
    else:
        vault = next((x for x in (target, *target.parents) if (x / ".obsidian").is_dir()), None)
        if vault is None:
            raise Invalid("Cannot identify vault root; ask user for --vault")
    vault = vault.resolve()
    target = target.resolve()
    if not target.is_relative_to(vault) or target == vault:
        raise Invalid("Choose a dedicated archive directory inside the vault")
    return validate({"schema_version": 1, "vault_root": str(vault), "archive_root": target.relative_to(vault).as_posix()})


def setup(destination, vault_root=None, explicit=None, replace=False):
    config = build(destination, vault_root)
    path = config_path(explicit)
    if path.resolve().is_relative_to(Path(config["vault_root"]).resolve()):
        raise Invalid("Keep shared local configuration outside the note vault")
    if path.exists():
        original = path.read_bytes()
        try:
            if json.loads(original.decode("utf-8")) == config:
                return {"saved": True, "unchanged": True, "config_path": str(path), **config}
        except (ValueError, UnicodeError):
            pass
        if not replace:
            raise Invalid("Existing configuration differs; --replace requires user-requested path change")
    else:
        original = None
    path.parent.mkdir(parents=True, exist_ok=True)
    reject_links(path)
    data = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=".task-memory-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        reject_links(path)
        if original is None:
            os.link(name, path)
        else:
            if path.read_bytes() != original:
                raise Invalid("Configuration changed concurrently; reread before replacing")
            os.replace(name, path)
        if path.read_bytes() != data:
            raise Invalid("Configuration readback mismatch")
    finally:
        Path(name).unlink(missing_ok=True)
    return {"saved": True, "unchanged": False, "config_path": str(path), **config}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show")
    show.add_argument("--config")
    create = commands.add_parser("setup")
    create.add_argument("--config")
    create.add_argument("--destination", required=True)
    create.add_argument("--vault")
    create.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        result = describe(args.config) if args.command == "show" else setup(args.destination, args.vault, args.config, args.replace)
    except (OSError, ValueError, TypeError) as error:
        result = {"error": str(error), "needs_setup": True}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
