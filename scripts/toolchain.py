"""Resolve official Godot releases and host tools without changing the machine's default editor."""
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

CACHE = Path(os.environ.get("GODOT_GATEWAY_CACHE", Path.home()/".cache"/"godot-three-gateway"))


def host():
    system = {"Windows":"windows","Darwin":"macos","Linux":"linux"}[platform.system()]
    machine = platform.machine().lower()
    arch = {"amd64":"x86_64","x86_64":"x86_64","arm64":"arm64","aarch64":"arm64"}.get(machine)
    if not arch:
        raise ValueError(f"Unsupported editor architecture: {machine}")
    return system, arch


def api(url):
    request = urllib.request.Request(url, headers={"User-Agent":"godot-three-gateway"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def download(asset, target):
    if target.is_file():
        return
    import tempfile
    target.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading", asset["name"], flush=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
        partial = Path(temp.name)
    try:
        with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response,out)
        if partial.stat().st_size != asset["size"]:
            raise ValueError("Incomplete download")
        if asset.get("digest"):
            with partial.open("rb") as source:
                digest = hashlib.file_digest(source,"sha256").hexdigest()
            if "sha256:"+digest != asset["digest"]:
                raise ValueError("Release checksum mismatch")
        os.replace(partial,target)
    finally:
        partial.unlink(missing_ok=True)


def editor(explicit=None,tag=None):
    if explicit:
        found = shutil.which(str(explicit)) or str(Path(explicit).resolve(strict=True))
        return Path(found)
    base = "https://api.github.com/repos/godotengine/godot-builds/releases/"
    release = api(base+"tags/"+tag) if tag else api("https://api.github.com/repos/godotengine/godot/releases/latest")
    tag = release["tag_name"]
    directory = CACHE/tag
    system, arch = host()
    suffix = {"windows": "_win64.exe.zip" if arch=="x86_64" else "_windows_arm64.exe.zip",
              "linux": "_linux."+arch+".zip", "macos":"_macos.universal.zip"}[system]
    asset = next(a for a in release["assets"] if a["name"].endswith(suffix) and "_mono_" not in a["name"])
    archive = directory/asset["name"]
    download(asset,archive)
    with zipfile.ZipFile(archive) as z:
        if system == "macos":
            binary = directory/"Godot.app/Contents/MacOS/Godot"
            if not binary.exists(): subprocess.run(["ditto","-x","-k",archive,directory],check=True)
        else:
            name = next(n for n in z.namelist() if n.endswith("_console.exe" if system=="windows" else "_linux."+arch))
            binary = directory/name
            if not binary.exists():
                z.extract(name,directory)
                if system == "windows":
                    z.extract(name.replace("_console.exe",".exe"),directory)
                else:
                    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def template_for(engine):
    version = subprocess.check_output([engine,"--version"],text=True).strip()
    match = re.match(r"^(\d+\.\d+(?:\.\d+)?)\.(stable|beta\d+|rc\d+|dev\d+)\.official\.",version)
    if not match:
        raise ValueError("Supply --template from the same build as your custom Godot editor.")
    number, channel = match.groups()
    tag = f"{number}-{channel}"
    name = "web_dlink_nothreads_release.zip"
    dirs = [Path(os.environ.get("APPDATA",Path.home()))/"Godot/export_templates",
            Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local/share"))/"godot/export_templates",
            Path.home()/"Library/Application Support/Godot/export_templates"]
    for directory in dirs:
        file = directory/f"{number}.{channel}"/name
        if file.is_file(): return file
    destination = CACHE/tag/name
    if not destination.is_file():
        release = api("https://api.github.com/repos/godotengine/godot-builds/releases/tags/"+tag)
        asset = next(a for a in release["assets"] if a["name"].endswith("_export_templates.tpz") and "_mono_" not in a["name"])
        archive = CACHE/tag/asset["name"]
        download(asset,archive)
        with zipfile.ZipFile(archive) as z:
            member = next(n for n in z.namelist() if n.endswith("/"+name))
            destination.write_bytes(z.read(member))
    return destination
