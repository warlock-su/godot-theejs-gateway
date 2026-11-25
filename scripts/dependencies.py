"""Resolve once per project. Cargo and npm lockfiles are retained with the installed addon."""
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from toolchain import api, host

ASSETS = Path(__file__).resolve().parents[1]/"assets"


def run(args, cwd=None):
    print("+", *map(str,args),flush=True)
    subprocess.run(args,cwd=cwd,check=True)


def copy_sources(src, dst):
    shutil.copytree(src,dst,dirs_exist_ok=True,ignore=shutil.ignore_patterns(
        "Cargo.lock","package-lock.json","target","node_modules","dist","*.uid","*.import"))


def locked(src, dest, update):
    if src.is_file() and not update: shutil.copy2(src,dest)
    else: dest.unlink(missing_ok=True)


def viewer(work, locks, output, update):
    npm=shutil.which("npm.cmd") or shutil.which("npm")
    if not npm: raise ValueError("Install Node.js LTS with npm, then retry.")
    directory=work/"viewer"
    copy_sources(ASSETS/"viewer",directory)
    lock=directory/"package-lock.json"
    locked(locks/lock.name,lock,update)
    run([npm,"ci" if lock.exists() else "install","--no-audit","--no-fund"],directory)
    run([npm,"run","build"],directory)
    output.mkdir(parents=True,exist_ok=True)
    for name in ("index.html","game.css"): shutil.copy2(directory/name,output/name)
    shutil.copy2(directory/"dist/gateway.js",output/"gateway.js")
    shutil.copy2(directory/"node_modules/three/LICENSE",output/"THREE-LICENSE.txt")
    return lock


def rust(work, locks, update, web=False):
    cargo=shutil.which("cargo")
    if not cargo: raise ValueError("Install Rust with rustup, add Cargo to PATH, then retry.")
    source=work/"bridge"
    copy_sources(ASSETS/"bridge",source)
    directory=source/"web" if web else source
    lock=directory/"Cargo.lock"
    locked(locks/("web.lock" if web else "native.lock"),lock,update)
    if not lock.exists(): run([cargo,"generate-lockfile"],directory)
    build_dir=Path(os.environ.get("CARGO_TARGET_DIR",work/"target")).resolve()
    if web:
        target="wasm32-unknown-emscripten"
        cmd=[cargo,"+nightly","rustc","--locked","--release","--target",target,
             "--target-dir",build_dir,"-Zbuild-std=std,panic_abort","--","-C","link-arg=-O1"]
        env=os.environ.copy()
        if os.name=="nt" and shutil.which("emcc.exe"):
            env.setdefault("CARGO_TARGET_WASM32_UNKNOWN_EMSCRIPTEN_LINKER","emcc.exe")
        # Keep the dependency resolver's diagnostics when a new release breaks on wasm32.
        with tempfile.TemporaryFile(mode="w+",encoding="utf-8") as log:
            result=subprocess.run(cmd,cwd=directory,env=env,stdout=log,stderr=subprocess.STDOUT)
            log.seek(0)
            message=log.read()
            print(message[-8000:],flush=True)
        if result.returncode:
            if "RustVariant" not in message or "OpaqueVariant" not in message or "E0080" not in message:
                raise RuntimeError("Wasm build failed; inspect the compiler diagnostic above.")
            version=next(p["version"] for p in tomllib.loads(lock.read_text())["package"] if p["name"]=="godot")
            def numbers(v): return tuple(map(int,v.split(".")))
            prior=[v["num"] for v in api("https://crates.io/api/v1/crates/godot")["versions"]
                   if not v["yanked"] and v["num"].replace(".","").isdigit()
                   and numbers(v["num"])[:2]==numbers(version)[:2] and numbers(v["num"])<numbers(version)]
            if not prior: raise RuntimeError(f"No previous stable patch for godot {version}")
            fallback=max(prior,key=numbers)
            print(f"wasm32 Variant layout failed with {version}; retrying {fallback}",flush=True)
            run([cargo,"update","-p","godot","--precise",fallback],directory)
            subprocess.run(cmd,cwd=directory,env=env,check=True)
        return build_dir/target/"release/godot_three_gateway.wasm",lock
    run([cargo,"build","--release","--locked","--target-dir",build_dir],directory)
    system,_=host()
    filename={"windows":"godot_three_gateway.dll","linux":"libgodot_three_gateway.so",
              "macos":"libgodot_three_gateway.dylib"}[system]
    return build_dir/"release"/filename,lock
