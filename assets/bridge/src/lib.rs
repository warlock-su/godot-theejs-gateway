use godot::classes::{Engine, Input, ProjectSettings, Time};
use godot::prelude::*;
mod pose;
#[cfg(not(target_os = "emscripten"))]
mod server;
#[cfg(target_os = "emscripten")]
#[path = "browser.rs"]
mod server;
use pose::Scene;
use server::Server;

struct ThreeGodotExtension;

#[gdextension]
unsafe impl ExtensionLibrary for ThreeGodotExtension {}

#[derive(GodotClass)]
#[class(base=Node, init)]
struct ThreeGatewayBridge {
    base: Base<Node>,
    scene: Option<Scene>,
    server: Option<Server>,
    sequence: u32,
    last_tick: Option<u64>,
    applied: u8,
    actions: Vec<StringName>,
}

#[godot_api]
impl INode for ThreeGatewayBridge {
    fn ready(&mut self) {
        self.base_mut().set_process_priority(i32::MAX);
        self.base_mut().set_physics_process_priority(-100);
        let port = std::env::var("GODOT_GATEWAY_PORT").ok()
            .and_then(|s| s.parse::<u16>().ok()).unwrap_or(8767);
        self.actions = ["left", "right", "forward", "back", "jump"].iter().map(|action| {
            let default_name = format!("gateway_{action}");
            let setting = format!("three_gateway/actions/{action}");
            let name = ProjectSettings::singleton().get_setting_ex(&setting)
                .default_value(&default_name.to_variant()).done().to::<GString>();
            StringName::from(&name)
        }).collect();
        let session = format!(
            "rust-{}-{}",
            std::process::id(),
            Time::singleton().get_ticks_usec()
        );
        let result = Scene::discover(self.base().get_parent().unwrap(), &session).and_then(
            |(scene, manifest, assets)| {
                let server = Server::start(port, session, manifest, assets)
                    .map_err(|err| err.to_string())?;
                Ok((scene, server))
            },
        );
        match result {
            Ok((scene, server)) => {
                self.scene = Some(scene);
                self.server = Some(server);
                #[cfg(not(target_os = "emscripten"))]
                godot_print!("Three.js / Rust GDExtension — http://127.0.0.1:{port}/");
            }
            Err(error) => {
                godot_error!("Rust bridge startup failed: {error}");
                self.base().get_tree().quit_ex().exit_code(1).done();
            }
        }
    }

    fn physics_process(&mut self, _: f64) {
        if let Some(server) = &self.server {
            self.apply_keys(server.keys());
        }
    }

    fn process(&mut self, _: f64) {
        let (Some(scene), Some(server)) = (&self.scene, &self.server) else {
            return;
        };
        if !server.subscribed() {
            return;
        }
        let tick = Engine::singleton().get_physics_frames();
        if self.last_tick == Some(tick) {
            return;
        }
        if let Some(packet) = scene.capture(self.sequence, tick as u32) {
            server.publish(packet);
            self.last_tick = Some(tick);
            self.sequence = self.sequence.wrapping_add(1);
        }
    }

    fn exit_tree(&mut self) {
        self.server.take();
        self.apply_keys(0);
        self.scene.take();
    }
}

impl ThreeGatewayBridge {
    fn apply_keys(&mut self, mask: u8) {
        let changed = mask ^ self.applied;
        if changed == 0 {
            return;
        }
        let mut input = Input::singleton();
        for (i, action) in self.actions.iter().enumerate() {
            let bit = 1 << i;
            if changed & bit == 0 {
                continue;
            }
            if mask & bit != 0 {
                input.action_press(action);
            } else {
                input.action_release(action);
            }
        }
        self.applied = mask;
    }
}
