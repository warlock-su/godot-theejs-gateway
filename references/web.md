# Export a browser-local game

Run `install` first. The native preview is useful for checking camera placement, the material adapters and input before building WebAssembly. Web export needs a Godot project whose gameplay scripts and other extensions can also run in a standard web template; check those dependencies separately in projects using .NET.

## Install the current toolchain

Use Python 3.11 or later, Node.js LTS with npm, and Rust stable with the host linker. Use rustup to add the current nightly, Rust standard-library sources, and the Emscripten target. Install the Emscripten SDK in a tools directory outside the game.

```sh
rustup toolchain install nightly --profile minimal --component rust-src --target wasm32-unknown-emscripten
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh
emcc --version
```

On Windows, use an SDK command prompt, `emsdk.bat` and `emsdk_env.bat`, or source the corresponding `emsdk_env.ps1` in PowerShell. On macOS install the Xcode command line tools. On Linux install a C/C++ linker for the host. Run the gateway commands in the environment with `cargo`, `node`, `npm` and `emcc` available. [Rust installers](https://rustup.rs/), [Node.js downloads](https://nodejs.org/en/download), [Emscripten SDK](https://emscripten.org/docs/getting_started/downloads.html), [godot-rust web target](https://godot-rust.github.io/book/toolchain/export-web.html).

## Build, serve and exercise input

```sh
python scripts/gateway.py web --project "../My Game" --out "../My Game Web"
python -m http.server 8000 --bind 127.0.0.1 --directory "../My Game Web"
```

Open [the local game](http://127.0.0.1:8000/). For the starter, run the following from another terminal. The test checks a rendered frame, Godot physics ticks, simultaneous stick and jump input, landing, and fullscreen after disconnecting browser networking.

```sh
python scripts/smoke.py http://127.0.0.1:8000/ --backend wasm --touch
```

Serve the output on HTTPS for phone testing. Keep the JS, Wasm, PCK, CSS, models and licenses together under the same URL directory. Serve `.wasm` as `application/wasm`, JavaScript as JavaScript, and `.pck` as `application/octet-stream`. A single-threaded template works without a shared-memory worker. Compression should be applied once. Try the published URL with the network switched offline after loading, then on a physical phone to measure its real FPS. Touch emulation verifies input and layout.

## Editor and dependency selection

The first blank installation resolves the latest stable Godot release, stable crates and npm packages. The project records editor identity, native Cargo resolution and npm resolution in `addons/three_gateway/locks/`. A successful web export writes its own `web.lock`. Retain these files with the game. Use `--update` on the relevant command to deliberately resolve new releases, and rerun the browser tests. An existing editor can be selected with `--godot`. `GODOT_GATEWAY_CACHE` controls the shared download location.

The exporter first looks for the matching editor's installed `web_dlink_nothreads_release.zip`. Otherwise it downloads the official template archive corresponding to the same tag, verifies the GitHub digest when supplied, and extracts the web template. The entire official archive can be over a gigabyte. Use `--template path/to/template.zip` for a custom editor or a locally built template. Build a custom release template from **the same Godot source revision** with `platform=web target=template_release threads=no dlink_enabled=yes`. Check that revision's Emscripten requirements. If the source calls the web display resize method unconditionally in a headless loop, [this optional patch](headless-web.patch) shows the guarded call. Check applicability to the chosen source tree with `git apply --check --unidiff-zero`. The stock template passed the starter test on the verified setup.

Rust uses the same scene capture and binary layout in native and browser builds. The web profile uses abort-on-panic to avoid importing an exception tag that a release template may omit. The installer tries the current Rust binding first. If its wasm32 size/alignment assertion for `RustVariant` fails, it reports the error and tries the previous published patch in the same series. Any other compilation error remains visible. Pass `--web-lock path/to/web.lock` to reproduce a verified resolution.

## Existing scenes

`--scene res://levels/arena.tscn` selects the starting scene. The exporter gathers reachable models and preserves their relative paths in `models/`. Pass `--extra-resource res://props/chest.glb` for assets reached through dynamically constructed paths, and include additional scenes loaded at runtime in the same way. Export runs in a disposable staging project. Custom export plugins, hidden source directories, external asset dependencies and generated runtime resources can require project-specific staging changes.

The general exporter retains Godot's imported meshes and packages original GLBs for Three.js. Large games can reduce duplicate data by generating simulation-only GLBs that retain node names, skins, inverse bind matrices and animation tracks. Check bone names, packet size and sampled movement against the full imports before using the stripped assets. Downsample mobile render textures separately when that quality tradeoff is desired.
