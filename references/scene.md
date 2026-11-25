# Scene contract

The runner opens the selected game as the real `SceneTree.current_scene`. Its persistent listener attaches a bridge when Godot changes scenes. The native service binds only to loopback. It serves a manifest, an allowlist of model assets, a pose socket and an input socket. Each viewer acknowledges a pose before receiving the newest one. Idle clients cannot queue an unbounded backlog.

## Scene content

* An enabled Camera3D supplies the transform and projection. Add one to scenes created from an empty 3D root. Canvas aspect changes preserve the vertical framing of the source projection.
* BoxMesh and horizontal PlaneMesh instances carry size, transform, visibility, albedo, metallic and roughness. A primitive without a StandardMaterial3D gets the default material. DirectionalLight3D, OmniLight3D and WorldEnvironment supply lighting and background. The viewer maps sun shadows to a PCF shadow map.
* Use embedded, self-contained GLB files for general triangle meshes, textures and skinned characters. Each instance can have one Skeleton3D. Bone names must match between Godot and Three.js. Split multiple rigs into separate model scenes. Native routes are assigned per instance. The static exporter preserves relative paths so names may repeat in different directories.
* Godot runs animations. Each pose contains a root matrix and twelve floats per bone, relative to its bind pose. Add one controlled GLB root to the `gateway_player` group to interpolate camera, root and joints against the same physics clock.
* Adding or removing renderable nodes schedules rediscovery. The native page reconnects and reloads its assets; the web export replaces its current view. Frequent spawning in a large game benefits from an incremental object-lifetime protocol. Godot scripts, physics bodies and collisions execute normally even when their effects have no Three.js visual mapping.
* Custom shaders, particles, Godot UI, spotlights, arbitrary procedural ArrayMeshes, blend shapes and per-instance overrides of imported GLB materials need explicit adapters. The native Godot viewport is the reference for testing its renderer and UI.

## Input

The gateway sends five held bits in order: left, right, forward, back, jump. Quick jump presses are latched until the next physics step. Keyboard and touch use the same Godot Input actions. To use an existing controller, add these project settings under `[three_gateway]` in `project.godot`, substituting its actual action names.

```ini
[three_gateway]
actions/left="move_left"
actions/right="move_right"
actions/forward="move_forward"
actions/back="move_back"
actions/jump="jump"
```

Default names are `gateway_left`, `gateway_right`, `gateway_forward`, `gateway_back`, and `gateway_jump`. The starter uses those defaults. A native Godot editor run can keep its normal bindings.

## Measurements

The HUD counts completed Three.js render callbacks. `window.threeGame.snapshot()` returns the backend, drawing-buffer size, Godot physics tick and a representative world position. Keep viewport size, pixel ratio, camera, lighting, assets and scripted input equal. Warm shaders before timing. Run one renderer at a time, alternate process order and report multiple intervals and their spread. For bridge-only cost, capture real binary packets, feed them into the same decoder at the same physics rate and compare with live delivery. An entire game-loop measurement includes simulation, transport, drawing and browser scheduling.

## Connecting a different renderer

Fetch `/scene` to obtain the session ID, ordered model descriptions, primitive kinds, light counts, packet size and optional player interpolation clock. Connect to `/poses?session=ID` and acknowledge each received binary packet with the single byte `01`. Separately send a one-byte held-action mask to `/input?session=ID`. Re-fetch the manifest when reconnecting after a scene change. The wasm route uses the same manifest and packets through `JavaScriptBridge`.

Protocol version 1 begins with five little-endian unsigned 32-bit words: magic `0x31505347`, sequence, physics tick, source width and source height. The following table is in float32 words. Matrices are column-major. A flag is a float with value zero or one.

| Block, in order | Words per entry | Layout |
| --- | ---: | --- |
| Camera and environment | 39 | Camera world matrix, projection matrix, background RGB, ambient RGB, ambient energy |
| Primitive | 26 | Dimensions (3), world matrix (16), RGB (3), metallic, roughness, visible, casts shadow |
| Directional light | 9 | Direction (3), RGB (3), energy, shadows enabled, visible |
| Omni light | 8 | World position (3), RGB (3), energy, range |
| GLB instance | 17 + 12 per bone | Root world matrix, visible, then bind-relative bone transforms in manifest order |

A bone transform contains its three basis columns followed by its origin, three floats each. The viewer composes `modelWorld × boneDelta × bindWorld`. The Rust [producer](../assets/bridge/src/pose.rs) and JS [decoder](../assets/viewer/poses.js) both compute the declared packet length. Change the protocol version if the layout changes.
