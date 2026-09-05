"""Source / packaged artifact acceptance with only task-private output paths."""

from __future__ import annotations

import argparse
import grp
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    artifact_options = parser.add_mutually_exclusive_group(required=True)
    artifact_options.add_argument("--pyz", type=Path)
    artifact_options.add_argument("--executable", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    composer = args.development / "stack-composer"
    fixtures = composer / "tests/fixtures"
    blueprint = args.development / "stack-content/pilots/cse-pilot"
    values_root = args.development / "hpc-lab/fixtures/workspace-init"
    # All generated deployment strings refer to the harness's private root.
    # The harness renders only; no Spack/build/module activation is executed.
    source = [sys.executable, "-m", "stack_composer"]
    packaged = (
        [sys.executable, "-S", str(args.pyz.resolve())]
        if args.pyz else [str(args.executable.resolve())]
    )
    environment = dict(os.environ, SHIV_ROOT=str(root / "shiv"), PYTHONDONTWRITEBYTECODE="1")

    def run(command, *arguments):
        child_environment = dict(environment, PYTHONNOUSERSITE="1")
        if command == packaged:
            child_environment.pop("PYTHONPATH", None)
            if args.executable:
                child_environment.update(PATH="/no-host-python", PYTHONHOME="/no-host-python")
        result = subprocess.run(
            [*command, *map(str, arguments)],
            env=child_environment,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise AssertionError(f"{arguments[0]} failed: {result.stdout}\n{result.stderr}")
        return result.stdout

    def inventory(directory):
        return {
            p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file()
        }

    common = [
        "--templates",
        fixtures / "template-sets",
        "--release",
        "audit",
        "--rendered-at",
        "2026-09-04T00:00:00Z",
        "--source-repo",
        "local://stack-composer-assessment",
        "--source-commit",
        "a" * 40,
    ]
    results = []
    for shape in ["example-linux", "example-cray"]:
        profile = fixtures / "profiles" / shape / "profile.yaml"
        static_args = [
            "render-static",
            "--profile",
            profile,
            *common,
            "--output-root",
            root / "catalogs",
        ]
        catalog = Path(run(source, *static_args).strip())
        expected = inventory(catalog)
        run(packaged, *static_args, "--overwrite")
        assert inventory(catalog) == expected, "source / artifact static bytes differ"
        full_args = [
            "render",
            "--profile",
            profile,
            *common,
            "--deployment",
            fixtures / "deployments" / f"{shape}.yaml",
            "--stack",
            fixtures / "stacks/science-stack/stack.yaml",
            "--package-sets",
            fixtures / "package-sets",
            "--package-repos",
            fixtures / "package-repos",
            "--output-root",
            root / "full",
        ]
        full = Path(run(source, *full_args).strip())
        expected_full = inventory(full)
        run(packaged, *full_args, "--overwrite")
        assert inventory(full) == expected_full, "source / artifact full workspace bytes differ"
        values = root / f"{shape}-values.yaml"
        values.write_text(
            (values_root / f"{shape.removeprefix('example-')}-values.yaml")
            .read_text()
            .replace("/shared/tests/workspace-init", str(root / "deployment"))
            .replace("/tmp/hpc-lab-cse", str(root / "stages"))
        )
        workspace = root / "initialized" / shape
        init_args = [
            "init-workspace",
            "--blueprint",
            blueprint,
            "--catalog",
            catalog,
            "--values",
            values,
            "--output",
            workspace,
        ]
        run(source, *init_args)
        expected_init = inventory(workspace)
        run(packaged, *init_args, "--overwrite")
        assert inventory(workspace) == expected_init, "source / artifact initializer bytes differ"
        for filename in ("cse-build", "env/setup-build-env.sh"):
            check = subprocess.run(["bash", "-n", str(workspace / filename)], capture_output=True)
            assert check.returncode == 0, check.stderr
        results.append(
            {
                "profile": shape,
                "static_files": len(expected),
                "full_files": len(expected_full),
                "initialized_files": len(expected_init),
                "byte_equal": True,
            }
        )
    linux_catalog = root / "catalogs/example-linux/static/audit"
    published = Path(
        run(
            packaged,
            "publish-static",
            "--catalog",
            linux_catalog,
            "--output-root",
            root / "published",
            "--published-at",
            "2026-09-04T00:00:00Z",
            "--reviewed-by",
            "assessment",
            "--approved-by",
            "assessment",
            "--set-current",
            "--group",
            grp.getgrgid(os.getgid()).gr_name,
        ).strip()
    )
    run(
        packaged,
        "init-workspace",
        "--blueprint",
        blueprint,
        "--catalog",
        published,
        "--values",
        root / "example-linux-values.yaml",
        "--output",
        root / "from-publication",
    )
    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "results": results,
                "publication_to_workspace": "passed",
                "root": str(root),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
