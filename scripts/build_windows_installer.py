"""Build the private Windows installer payload and Inno Setup executable.

The builder is intentionally offline: application files come from the public
distribution builder, and Python dependencies come only from the caller's
wheelhouse.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

VERSION = "0.3.2"
PYTHON_EMBED_SHA256 = '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'
PTH = "python313.zip\n.\n../app/scripts\n../app\nLib/site-packages\nimport site\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> Path:
    path = Path(name.replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe archive member: {name}")
    return path


def extract_archive(archive: Path, destination: Path, *, strip_root=True) -> list[Path]:
    """Extract regular files from a distribution ZIP under *destination*."""
    extracted = []
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            relative = _safe_member(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"symlink in archive: {info.filename}")
            # The public distribution has one deterministic top-level folder.
            parts = relative.parts
            if (strip_root and len(parts) < 2) or info.is_dir():
                continue
            target = destination.joinpath(*(parts[1:] if strip_root else parts))
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved = target.resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise ValueError(f"archive escapes payload: {info.filename}")
            with source.open(info) as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            extracted.append(target)
    return extracted


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _manifest(payload: Path, source_tree: str, python_embed: Path, output: Path) -> dict:
    files = {}
    for path in sorted(p for p in payload.rglob("*") if p.is_file()):
        relative = path.relative_to(payload).as_posix()
        files[relative] = {"sha256": sha256(path), "size": path.stat().st_size}
    tree = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schemaVersion": 1, "version": VERSION, "payloadFiles": files,
            "payloadTreeSha256": tree, "sourceTreeSha256": source_tree,
            "pythonEmbed": {"path": python_embed.name, "sha256": sha256(python_embed),
                             "size": python_embed.stat().st_size},
            "output": {"path": output.name, "sha256": sha256(output), "size": output.stat().st_size}}


def build(*, compiler: Path, python_embed: Path, output: Path, source_root: Path,
          wheelhouse: Path, installer_source: Path, version: str = VERSION,
          python_embed_sha256: str = PYTHON_EMBED_SHA256, verification_payload: Path | None = None) -> dict:
    if version != VERSION:
        raise ValueError(f"unsupported build version: {version}")
    if not compiler.is_file() or not python_embed.is_file():
        raise FileNotFoundError("compiler and embedded Python archive are required")
    if sha256(python_embed) != python_embed_sha256:
        raise ValueError('Embedded Python checksum does not match the trusted build input')
    requirements = [source_root / name for name in ('requirements-server.txt', 'requirements-images.txt', 'requirements-desktop.txt')]
    if not wheelhouse.is_dir() or any(not path.is_file() for path in requirements):
        raise FileNotFoundError("wheelhouse and pinned requirement files are required")
    output = output.resolve()
    if verification_payload is not None:
        verification_payload = verification_payload.resolve()
        if verification_payload.exists():
            raise ValueError('The verification payload destination must be new; existing files are preserved')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="project-hub-installer-") as temporary:
        scratch = Path(temporary)
        app = scratch / "payload" / "app"
        runtime = scratch / "payload" / "runtime"
        runtime.mkdir(parents=True)
        distribution = scratch / "distribution.zip"
        from build_project_hub_distribution import build as build_distribution
        distribution_info = build_distribution(distribution, root=source_root, standalone=True)
        extract_archive(distribution, app)
        extract_archive(python_embed, runtime, strip_root=False)
        python_exe = runtime / "python.exe"
        if not python_exe.is_file():
            raise ValueError("embedded archive does not contain python.exe")
        (runtime / "python313._pth").write_text(PTH, encoding="ascii", newline="\n")
        site_packages = runtime / "Lib" / "site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        for requirement in requirements:
            _run([sys.executable, "-m", "pip", "--isolated", "install", "--no-index",
                  "--find-links", str(wheelhouse), "--only-binary", ":all:",
                  "--platform", "win_amd64", "--python-version", "3.13", "--implementation", "cp", "--abi", "cp313", "--no-compile",
                  "--target", str(site_packages), "-r", str(requirement)])
        (scratch / "payload" / "project-hub.cmd").write_text(
            '@"%~dp0runtime\\python.exe" -B "%~dp0app\\scripts\\hub_cli.py" %*\n',
            encoding="ascii", newline="\r\n")
        for name in ("brand.ico", "wizard.bmp", "wizard-small.bmp"):
            shutil.copy2(installer_source / name, scratch / name)
        shutil.copy2(installer_source / 'brand.ico', scratch / 'payload' / 'brand.ico')
        program_files = {path.relative_to(scratch / 'payload').as_posix():sha256(path)
                         for path in sorted((scratch / 'payload').rglob('*')) if path.is_file()}
        (scratch / 'payload' / 'distribution.json').write_text(
            json.dumps({'schemaVersion':1, 'version':version, 'files':program_files,
                        'sourceTreeSha256':distribution_info['sourceTreeSha256']}, sort_keys=True) + '\n', encoding='utf-8')
        shutil.copy2(installer_source / "project-hub.iss", scratch / "project-hub.iss")
        _run([str(compiler), f"/DPayloadDir={scratch / 'payload'}",
              f"/DOutputDir={output}", f"/DBuildVersion={version}",
              str(scratch / "project-hub.iss")])
        executable = output / f"ProjectHub-{version}.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"compiler did not produce {executable}")
        manifest = _manifest(scratch / "payload", distribution_info["sourceTreeSha256"], python_embed, executable)
        manifest_path = output / f"ProjectHub-{version}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if verification_payload is not None:
            shutil.copytree(scratch / 'payload', verification_payload)
        return {"output": str(executable), "manifest": str(manifest_path), "sha256": manifest["output"]["sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--python-embed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--installer-source", type=Path, default=Path(__file__).resolve().parents[1] / "installer")
    parser.add_argument("--build-version", default=VERSION)
    parser.add_argument("--verification-payload", type=Path,
                        help="Keep the exact compiled payload in a new directory for isolated runtime verification")
    args = parser.parse_args(argv)
    print(json.dumps(build(compiler=args.compiler, python_embed=args.python_embed, output=args.output,
                           source_root=args.source_root.resolve(), wheelhouse=args.wheelhouse.resolve(),
                           installer_source=args.installer_source.resolve(), version=args.build_version,
                           verification_payload=args.verification_payload), indent=2))


if __name__ == "__main__":
    main()
