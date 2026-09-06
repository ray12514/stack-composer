"""Two-container workspace handoff model; never use an existing trial workspace.

Producer mounts sources at /inputs/sources, delivered tools at /tools, and an
empty scratch directory at /origin. Receiver mounts only the moved workspaces
at /received, tools, /site and the explicitly supplied /runtime prerequisites.
The partial/complete lock files below are preservation fixtures, NOT build evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str], **kwargs) -> str:
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
    )
    if result.returncode:
        raise RuntimeError(f"command failed: {command}\n{result.stdout}")
    return result.stdout


def inventory(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.exists() or not path.resolve().is_relative_to(root):
                raise ValueError(f"broken or escaping workspace link: {path}")
            result[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            result[name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mode": path.stat().st_mode & 0o7777,
            }
    return result


def produce() -> None:
    sources = Path("/inputs/sources")
    composer = sources / "stack-composer"
    content = sources / "stack-content"
    origin = Path("/origin")
    if list(origin.iterdir()):
        raise ValueError("producer origin must be empty")
    tools = [["/tools/native/stack-composer"], [sys.executable, "/tools/stack-composer.pyz"]]
    for tool in tools:
        run([*tool, "--help"])
        run([*tool, "--licenses"])
    receipt = {"lock_fixtures_are_not_build_evidence": True, "workspaces": {}}
    for shape, tool in zip(("linux", "cray"), tools):
        raw = (composer / f"tests/fixtures/portability/{shape}-values.yaml").read_text()
        raw = raw.replace("/shared/tests/workspace-init", "/site")
        raw = raw.replace("/tmp/hpc-lab-cse", "/site/stages")
        raw = raw.replace("group: hpc", "group: root")
        raw = raw.replace("/opt/spack", "/runtime/spack")
        raw = raw.replace(
            "https://github.com/spack/spack-packages.git", "file:///runtime/spack-packages"
        )
        values = origin / f"{shape}-values.yaml"
        values.write_text(raw)
        run(
            [
                *tool,
                "render-static",
                "--profile",
                str(composer / f"tests/fixtures/profiles/example-{shape}/profile.yaml"),
                "--templates",
                str(content / "templates"),
                "--output-root",
                str(origin / "catalogs"),
                "--release",
                "lab",
                "--rendered-at",
                "1970-01-01T00:00:00Z",
                "--source-repo",
                "local://offline-model",
                "--source-commit",
                "0" * 40,
            ]
        )
        catalog = origin / f"catalogs/example-{shape}/static/lab"
        if shape == "linux":
            run(
                [
                    *tool,
                    "publish-static",
                    "--catalog",
                    str(catalog),
                    "--output-root",
                    str(origin / "published"),
                    "--published-at",
                    "1970-01-01T01:00:00Z",
                    "--reviewed-by",
                    "Model review",
                    "--approved-by",
                    "Model approval",
                    "--group",
                    "root",
                    "--set-current",
                ]
            )
            catalog = origin / f"published/example-{shape}/static/lab"
        for state, count in (("fresh", 0), ("partial", 1), ("complete", 8)):
            name = f"{shape}-{state}"
            workspace = origin / "workspaces" / name
            run(
                [
                    *tool,
                    "init-workspace",
                    "--blueprint",
                    str(content / "pilots/cse-pilot"),
                    "--catalog",
                    str(catalog),
                    "--values",
                    str(values),
                    "--output",
                    str(workspace),
                ]
            )
            environments = sorted(workspace.glob("environments/*/*/spack.yaml"))
            if len(environments) != 8:
                raise ValueError(f"expected eight environments: {name}")
            for environment in environments[:count]:
                lock = environment.with_name("spack.lock")
                lock.write_text(json.dumps({"portability_preservation_fixture": name}) + "\n")
                lock.chmod(0o660)
            receipt["workspaces"][name] = inventory(workspace)
    # The receiver sees only this subtree, not catalogs, input values, or source repos.
    (origin / "workspaces/BEFORE-MOVE.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Produced six isolated model workspaces and pre-move inventories.")


def receive() -> None:
    for unavailable in ("/origin", "/inputs", "/Users/ravonventers/Development"):
        if Path(unavailable).exists():
            raise ValueError(f"original source path is unexpectedly available: {unavailable}")
    root = Path("/received")
    receipt = json.loads((root / "BEFORE-MOVE.json").read_text())
    report = {
        "source_directories_unavailable": True,
        "workspaces": {},
        "scope": "configuration and preservation model; no HPC package builds",
    }
    env = dict(
        os.environ,
        HOME="/tmp/portability-home",
        USER="root",
        WORKDIR="/site/work",
        PYTHONDONTWRITEBYTECODE="1",
        SPACK_DISABLE_LOCAL_CONFIG="true",
        SPACK_ROOT="/runtime/spack",
        GIT_CONFIG_COUNT="2",
        GIT_CONFIG_KEY_0="safe.directory",
        GIT_CONFIG_VALUE_0="/runtime/spack",
        GIT_CONFIG_KEY_1="safe.directory",
        GIT_CONFIG_VALUE_1="/runtime/spack-packages",
    )
    Path(env["HOME"]).mkdir()
    Path(env["WORKDIR"]).mkdir(parents=True, exist_ok=True)
    for name, before in receipt["workspaces"].items():
        workspace = root / name
        if inventory(workspace) != before:
            raise ValueError(f"workspace changed in transit: {name}")
        for path in workspace.rglob("*"):
            if path.is_file() and (path.suffix == ".sh" or path.name == "cse-build"):
                if any(
                    prefix in path.read_text()
                    for prefix in ("/origin", "/inputs/sources", "/Users/ravonventers/Development")
                ):
                    raise ValueError(f"workspace control retains a source path: {path}")
        run([str(workspace / "cse-build"), "--help"], env=env)
        run(
            [sys.executable, str(workspace / "scripts/verify-lockfiles.py"), "--workspace-only"],
            env=env,
        )
        report["workspaces"][name] = {"inventory_preserved": True, "workspace_inputs": "pass"}
        if name.endswith("fresh"):
            for context in ("login", "compute"):
                output = run(
                    [str(workspace / "cse-build"), context, "status", "--spack-mode", "shared"],
                    env=env,
                )
                (root / f"{name}-{context}-status.txt").write_text(output)
                if "Concrete locks: 0/8" not in output:
                    raise ValueError(f"unexpected lock status: {name}")
            report["workspaces"][name]["real_spack_scope_preflight"] = "login and compute pass"
        else:
            report["workspaces"][name]["locks"] = "synthetic byte-preservation fixtures only"
    report["spack_version"] = run(["/runtime/spack/bin/spack", "--version"], env=env).strip()
    for key, path in (
        ("spack_commit", "/runtime/spack"),
        ("recipes_commit", "/runtime/spack-packages"),
    ):
        report[key] = run(["git", "-C", path, "rev-parse", "HEAD"], env=env).strip()
    (root / "PORTABILITY-RESULT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["produce"]:
        produce()
    elif sys.argv[1:] == ["receive"]:
        receive()
    else:
        raise SystemExit("usage: check-workspace-portability.py produce|receive")
