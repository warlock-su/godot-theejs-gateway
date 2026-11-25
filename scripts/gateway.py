"""Install the gateway, run a source project, or export a self-contained browser game."""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from dependencies import ASSETS, copy_sources, run, rust, viewer
from toolchain import editor, host, template_for

ADDON = Path("addons/three_gateway")
RUNNER = "res://addons/three_gateway/runner.tscn"
MARK = ".three-gateway.json"


def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)


def digest(file):
    with file.open("rb") as fp: return hashlib.file_digest(fp,"sha256").hexdigest()


def import_project(engine,project):
    args=[engine,"--headless","--path",project,"--editor","--import"]
    cache=project/".godot/extension_list.cfg"
    first_scan=not cache.exists()
    try: run(args)
    except subprocess.CalledProcessError as err:
        # Windows can unload a newly discovered GDExtension late in the first editor scan.
        # The subsequent scan loads it during engine startup. Require that scan to exit cleanly.
        if not (os.name=="nt" and first_scan and err.returncode & 0xffffffff==0xc0000005 and cache.is_file()): raise
        print("Retrying first editor import with the discovered extension registered.",flush=True)
        run(args)


def publish_tree(stage, target, managed=False):
    """Commit only a complete tree. Preserve unrelated project files and reject edit conflicts."""
    old={}
    if target.exists() and any(target.iterdir()):
        if not (target/MARK).is_file():
            raise ValueError(f"Destination already contains unrelated files: {target}")
        old=json.loads((target/MARK).read_text())["files"]
        for name,fingerprint in old.items():
            path=target/name
            if path.is_file() and digest(path)!=fingerprint:
                raise ValueError(f"Preserve or revert your local modification before reinstalling: {path}")
    files={p.relative_to(stage).as_posix():digest(p) for p in stage.rglob("*") if p.is_file()}
    if target.exists():
        for path in target.rglob("*"):
            if not path.is_file(): continue
            name=path.relative_to(target).as_posix()
            if name==MARK or name in old: continue
            if name in files or not managed and not name.endswith((".uid",".import")):
                raise ValueError(f"Unmanaged file in destination: {path}")
            copy(path,stage/name)
    (stage/MARK).write_text(json.dumps({"files":files},indent=2),encoding="utf-8")
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix=".gateway-swap-") as temp:
        backup=Path(temp)/"before"
        if target.exists(): target.rename(backup)
        try: stage.rename(target)
        except BaseException:
            if backup.exists(): backup.rename(target)
            raise


def install(project,work,engine,update):
    addon=project/ADDON
    locks=addon/"locks"
    lib,lock=rust(work,locks,update)
    system,arch=host()
    with tempfile.TemporaryDirectory(dir=work) as temp:
        stage=Path(temp)/"addon"
        copy_sources(ASSETS/"addon",stage)
        copy(ASSETS.parent/"LICENSE",stage/"LICENSE.txt")
        npm_lock=viewer(work,locks,stage/"view",update)
        copy(lib,stage/"bin"/f"{system}-{arch}"/lib.name)
        copy(lock,stage/"locks/native.lock")
        copy(npm_lock,stage/"locks"/npm_lock.name)
        (stage/"locks/.gdignore").touch()
        (stage/"view/.gdignore").touch()
        version=subprocess.check_output([engine,"--version"],text=True).strip()
        (stage/"locks/editor.json").write_text(json.dumps({"version":version}),encoding="utf-8")
        publish_tree(stage,addon,managed=True)
    if not (project/"project.godot").exists(): copy(ASSETS/"blank.godot",project/"project.godot")
    import_project(engine,project)


def stage_project(project,dest,output):
    def ignore(folder,names):
        ignored={n for n in names if n.startswith(".") or n in {"node_modules","target","__pycache__"}}
        ignored.update(n for n in names if (Path(folder)/n).resolve()==output)
        return ignored
    shutil.copytree(project,dest,ignore=ignore,dirs_exist_ok=True)
    # Restore import boundaries that are intentionally dotfiles.
    for root,dirs,files in os.walk(project):
        dirs[:]=[n for n in dirs if n not in ignore(root,dirs)]
        if ".gdignore" in files: (dest/Path(root).relative_to(project)/".gdignore").touch()


def export_web(project,work,engine,args):
    addon=project/ADDON
    output=args.out.resolve()
    if output==project or output in project.parents or output.is_relative_to(addon) or output.is_relative_to(work):
        raise ValueError("Choose a separate output folder for the static site.")
    template=args.template.resolve(strict=True) if args.template else template_for(engine)
    locks=addon/"locks"
    # Each web toolchain is recorded separately; local editor files and presets are left intact.
    web_locks=locks
    if args.web_lock:
        web_locks=work/"web-locks"
        copy(args.web_lock,web_locks/"web.lock")
    lib,lock=rust(work,web_locks,args.update,web=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp, tempfile.TemporaryDirectory(dir=output.parent,prefix=".gateway-web-") as publication:
        staging=Path(tmp)/"project"
        site=Path(publication)/"site"
        site.mkdir()
        stage_project(project,staging,output)
        copy(lib,staging/ADDON/"bin/web"/lib.name)
        copy(Path(__file__).with_name("export_dependencies.gd"),staging/ADDON/"export_dependencies.gd")
        import_project(engine,staging)
        resources=Path(tmp)/"dependencies.json"
        run([engine,"--headless","--path",staging,"--script","res://addons/three_gateway/export_dependencies.gd",
             "--",resources,args.scene or "",*args.extra_resource])
        info=json.loads(resources.read_text(encoding="utf-8"))
        roots=list(dict.fromkeys([RUNNER,"res://addons/three_gateway/listener.gd",
                                  "res://addons/three_gateway/bridge.gdextension",*info["roots"]]))
        params=','.join(json.dumps(s) for s in roots)
        preset=('[preset.0]\nname="Gateway Web"\nplatform="Web"\nrunnable=true\nexport_filter="resources"\ninclude_filter=""\nexclude_filter=""\n'
                f'export_files=PackedStringArray({params})\n[preset.0.options]\n'
                f'custom_template/release={json.dumps(template.as_posix())}\n'
                'variant/extensions_support=true\nvariant/thread_support=false\nhtml/export_icon=false\n')
        (staging/"export_presets.cfg").write_text(preset,encoding="utf-8")
        run([engine,"--headless","--path",staging,"--export-release","Gateway Web",site/"game.html"])
        for key in ("game.js","game.pck","game.wasm","game.side.wasm",lib.name):
            if not (site/key).is_file(): raise ValueError(f"Template did not export {key}")
        (site/"game.html").unlink()
        for f in (addon/"view").iterdir():
            if f.is_file() and not f.name.startswith("."): copy(f,site/f.name)
        copy(addon/"LICENSE.txt",site/"LICENSE.txt")
        copy(ASSETS.parent/"references/GODOT-LICENSE.txt",site/"GODOT-LICENSE.txt")
        for name in info["models"]:
            relative=Path(name.removeprefix("res://"))
            src=(project/relative).resolve()
            if not src.is_relative_to(project): raise ValueError(f"Model outside project: {name}")
            copy(src,site/"models"/relative)
        index=site/"index.html"
        page=index.read_text(encoding="utf-8").replace('data-backend="native"',
            'data-backend="wasm" data-scene="'+html.escape(info["roots"][0],quote=True)+'"')
        index.write_text(page.replace("<!-- GODOT_ENGINE -->",'<script src="./game.js"></script>'),encoding="utf-8")
        publish_tree(site,output)
    copy(lock,locks/"web.lock")
    print("Static site:",output,"\nResolved web dependencies:",locks/"web.lock")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for mode in ("install","run","web"):
        p=sub.add_parser(mode)
        p.add_argument("--project",type=Path,required=True)
        p.add_argument("--godot",help="Use an existing editor. Default: latest official stable.")
        if mode!="run": p.add_argument("--update",action="store_true",help="Resolve current dependency releases again.")
        if mode!="install": p.add_argument("--scene",help="Optional res:// scene path. Default: project main scene.")
        if mode=="run": p.add_argument("--port",type=int,default=8767,choices=range(1,65536),metavar="PORT")
        if mode=="web":
            p.add_argument("--out",required=True,type=Path)
            p.add_argument("--template",type=Path,help="Matching Godot single-threaded dlink release template ZIP.")
            p.add_argument("--web-lock",type=Path,help="A previously validated web Cargo.lock.")
            p.add_argument("--extra-resource",action="append",default=[],help="A res:// resource loaded dynamically. Repeat as needed.")
    args=parser.parse_args()
    project=args.project.resolve()
    if args.command=="install" and project.exists() and not (project/"project.godot").exists():
        others=[p for p in project.iterdir() if p.name not in {".godot",".git",".gitignore",".gitattributes"}]
        if others: raise ValueError("Select the directory containing project.godot, or an empty folder.")
    if args.command!="install" and not (project/ADDON/MARK).is_file():
        raise ValueError("Run install for this project first.")
    work=project/".godot/three_gateway"
    work.mkdir(parents=True,exist_ok=True)
    recorded=project/ADDON/"locks/editor.json"
    local=work/"editor-path.txt"
    explicit=args.godot
    tag=None
    if not explicit and recorded.is_file() and not (args.command=="install" and args.update):
        version=json.loads(recorded.read_text())["version"]
        binary=Path(local.read_text()) if local.is_file() else None
        if binary and binary.is_file() and subprocess.check_output([binary,"--version"],text=True).strip()==version:
            explicit=binary
        else:
            match=re.match(r"^(\d+\.\d+(?:\.\d+)?)\.(stable|beta\d+|dev\d+|rc\d+)\.official\.",version)
            if not match: raise ValueError("Supply --godot for the custom engine recorded by this project.")
            tag="-".join(match.groups())
    engine=editor(explicit,tag)
    print("Godot",subprocess.check_output([engine,"--version"],text=True).strip(),flush=True)
    if args.command=="install":
        install(project,work,engine,args.update)
        local.write_text(str(engine.resolve()),encoding="utf-8")
    elif args.command=="web": export_web(project,work,engine,args)
    else:
        env=dict(os.environ,GODOT_GATEWAY_PORT=str(args.port))
        command=[engine,"--headless","--disable-render-loop","--max-fps","60","--path",project,RUNNER]
        if args.scene: command+=["--","--gateway-scene="+args.scene]
        print(f"Open http://127.0.0.1:{args.port}/ once the scene is ready.",flush=True)
        subprocess.run(command,env=env,check=True)


if __name__=="__main__":
    try: main()
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as e: sys.exit(str(e))
