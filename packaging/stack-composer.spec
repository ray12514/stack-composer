# PyInstaller one-directory candidate. Never freeze persistent build/lib.
import os
from pathlib import Path

source = Path(os.environ["STACK_COMPOSER_NATIVE_SOURCE"])
package = source / "src/stack_composer"
datas = [
    (str(path), str(Path("stack_composer") / path.parent.relative_to(package)))
    for path in sorted(package.rglob("*"))
    if path.is_file() and path.suffix in {".json", ".toml", ".txt"}
]
a = Analysis(
    [str(package / "__main__.py")],
    pathex=[str(source / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "stack_composer.schemas",
        "stack_composer.resources",
        "stack_composer.resources.THIRD_PARTY_LICENSES",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="stack-composer",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, contents_directory="_internal",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="stack-composer")
