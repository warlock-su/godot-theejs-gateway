# godot-theejs-gateway

Run a Godot 3D game with a Three.js viewport. Godot owns the scene, physics, animation and input. A Rust GDExtension publishes binary transforms. The browser renders the latest pose at its own frame rate.

**Для запуска в новом проекте дайте агенту эту ссылку и попросите подключить gateway по SKILL.md, запустить сцену и проверить движение и прыжок.** В пустой папке установщик создаст минимальный Godot-проект. В существующем проекте он добавит аддон и сможет открыть текущую стартовую сцену.

## Quick start

Install Python 3.11+, Node.js LTS with npm, and stable Rust with Cargo and the native linker for your platform. On Windows use the Visual Studio C++ Build Tools and Windows SDK. Clone this repository **outside** your game project.

```sh
git clone https://github.com/warlock-su/godot-theejs-gateway.git
cd godot-theejs-gateway
python scripts/gateway.py install --project "../My Game"
python scripts/gateway.py run --project "../My Game"
```

Open [the local viewer](http://127.0.0.1:8767/). The starter cube moves with WASD and jumps with Space. The first install downloads the latest stable editor and resolves and builds the bridge and viewer. Stop and rerun the last command after changing gameplay. Use `--godot /path/to/editor` on both commands to use the editor selected by an existing project.

| Mode | Simulation | Renderer | Delivered to the player |
| --- | --- | --- | --- |
| Source preview | Native headless Godot and Rust | Three.js / WebGL 2 | Local viewer, loopback binary WebSocket |
| Static web export | Godot and Rust WebAssembly on the device | Three.js / WebGL 2 | HTML, JS, Wasm, PCK and referenced GLBs |

The static build includes the FPS counter, keyboard input, touch stick, jump and fullscreen. Follow the [web export procedure](references/web.md). For supported scene types, input mapping, animated models and performance testing see the [scene contract](references/scene.md).

The root of this repository is an installable [agent skill](SKILL.md). The gateway code and procedural starter scene are distributed under the [MIT license](LICENSE). Godot, Three.js, Rust crates and build tools retain their respective licenses.
