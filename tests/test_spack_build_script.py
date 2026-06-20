from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


def test_spack_build_runs_lanes_and_writes_publish_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    for lane in ("gcc/core", "cce/mpi-craympich"):
        env_dir = workspace / "environments" / lane
        env_dir.mkdir(parents=True)
        (env_dir / "spack.yaml").write_text("spack:\n  specs: []\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_log = tmp_path / "spack.log"
    fake_spack = fake_bin / "spack"
    fake_spack.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$SPACK_FAKE_LOG\"\n"
        "if [[ \"$1\" == \"--version\" ]]; then echo '1.1.1'; exit 0; fi\n"
        "for arg in \"$@\"; do\n"
        "  if [[ \"$arg\" == \"find\" ]]; then echo '/opt/spack/fake-root'; exit 0; fi\n"
        "done\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_spack.chmod(0o755)
    reports = tmp_path / "reports"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["SPACK_FAKE_LOG"] = str(fake_log)

    result = subprocess.run(
        [
            "scripts/spack-build",
            "--workspace",
            str(workspace),
            "--reports",
            str(reports),
            "--jobs",
            "2",
            "--buildcache",
            "payload=file:///cache/payload",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert str(reports) in result.stdout
    verify = yaml.safe_load((reports / "verify-results.yaml").read_text(encoding="utf-8"))
    assert verify["spack"]["version"] == "1.1.1"
    assert verify["lanes"]["gcc-core"]["install_root"] == "/opt/spack/fake-root"
    prereqs = yaml.safe_load(
        (reports / "platform-module-prereqs.yaml").read_text(encoding="utf-8")
    )
    assert prereqs == {"lanes": {"gcc-core": [], "cce-mpi-craympich": []}}
    buildcache = yaml.safe_load(
        (reports / "buildcache-destinations.yaml").read_text(encoding="utf-8")
    )
    assert buildcache["push_destinations"] == [
        {
            "name": "payload",
            "url": "file:///cache/payload",
            "lanes_pushed": ["cce-mpi-craympich", "gcc-core"],
        }
    ]
    log = fake_log.read_text(encoding="utf-8")
    assert "concretize --force" in log
    assert "install -j 2" in log
    assert "buildcache push --update-index file:///cache/payload" in log


def test_spack_build_help() -> None:
    result = subprocess.run(
        ["scripts/spack-build", "--help"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "--workspace DIR" in result.stdout
