---
name: godot-theejs-gateway
description: Connect a new or existing Godot 3D project to Three.js through a Rust GDExtension, run a live headless source preview, test gameplay in the browser, or export Godot and Rust to a self-contained WebAssembly game.
---

# Godot Three.js Gateway

Run the scripts relative to this skill's directory. When given only the repository URL, clone it outside the target project's resource tree and read this file. For persistent discovery, clone into the user's skills directory if requested.

1. Identify the target root containing `project.godot`, or use the requested empty directory. Inspect the main scene, imported models, camera, input actions, Godot edition and native extensions. Use the project's editor via `--godot` for existing projects. A blank project defaults to the current official stable Godot. Obtain Python 3.11+, Node.js LTS/npm, Rust stable and the platform linker from their official installers if missing. Check `python --version`, `npm --version`, `cargo --version`.
2. Run `python scripts/gateway.py install --project <project>`. This compiles the Rust extension, bundles Three.js locally, adds `addons/three_gateway` and imports the project. It creates a playable primitive scene when starting from an empty folder. An established project's normal play entry point stays available.
3. Start `python scripts/gateway.py run --project <project>` in a process you can stop. Open the printed loopback URL. Choose a different port with `--port`, or an alternative scene with `--scene res://path/to/scene.tscn`. Restart the process to read edited source. Reinstall after changing gateway code. Pass `--update` on install to intentionally refresh dependency locks.
4. Validate a visible frame, advancing physics ticks and real input. For the starter, install the test dependencies with `python -m pip install playwright pillow` and `python -m playwright install chromium`, then run `python scripts/smoke.py http://127.0.0.1:8767/ --backend native`. Supply `--channel chrome` for an installed Chrome or `--screenshot path.png` to save the frame. For an existing game, exercise its actual controls and inspect a screenshot; the starter's test expects a cube with specific movement.
5. For existing actions, unsupported materials, custom renderables, rigs, or paired measurements, use the [scene contract](references/scene.md). For browser-local simulation, mobile controls, template selection and an offline test, use [web export](references/web.md).

Report the resolved editor and library versions, the verified URL and which device and input path were exercised. Keep the demo project's artwork, local build caches, credentials and deployment configuration out of downstream distributions.
