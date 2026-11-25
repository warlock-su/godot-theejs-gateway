use crate::server::Assets;
use godot::classes::{
    BoxMesh, DirectionalLight3D, Engine, MeshInstance3D, OmniLight3D, PlaneMesh, ProjectSettings,
    Skeleton3D, StandardMaterial3D, Viewport, WorldEnvironment,
    geometry_instance_3d::ShadowCastingSetting, light_3d::Param,
};
use godot::prelude::*;
use serde_json::{Value, json};
use std::path::PathBuf;

struct Actor {
    root: Gd<Node3D>,
    rig: Option<Gd<Skeleton3D>>,
    inverse_rest: Vec<Transform3D>,
}

enum Shape {
    Plane(Gd<PlaneMesh>),
    Box(Gd<BoxMesh>),
}
struct Primitive {
    node: Gd<MeshInstance3D>,
    shape: Shape,
}

pub struct Scene {
    viewport: Gd<Viewport>,
    environment: Option<Gd<WorldEnvironment>>,
    primitives: Vec<Primitive>,
    suns: Vec<Gd<DirectionalLight3D>>,
    lamps: Vec<Gd<OmniLight3D>>,
    actors: Vec<Actor>,
    bytes: usize,
}

fn local_path(path: &str) -> PathBuf {
    ProjectSettings::singleton()
        .globalize_path(path)
        .to_string()
        .into()
}

impl Scene {
    pub fn discover(root: Gd<Node>, session: &str) -> Result<(Self, Vec<u8>, Assets), String> {
        let viewport = root.get_viewport().ok_or("Scene has no viewport")?;
        let mut environment = None;
        let mut actors = Vec::new();
        let mut primitives = Vec::new();
        let mut suns = Vec::new();
        let mut lamps = Vec::new();
        let mut models = Vec::new();
        let mut kinds = Vec::new();
        let mut motion = Value::Null;
        let mut assets = Assets::new();
        let descendants = root.find_children_ex("*").owned(false).done();
        for node in std::iter::once(root.clone()).chain(descendants.iter_shared()) {
            let path = node.get_scene_file_path().to_string();
            if path.to_ascii_lowercase().ends_with(".glb") {
                let model = node.cast::<Node3D>();
                let file = local_path(&path);
                let asset = file
                    .file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned();
                let skeletons = model
                    .find_children_ex("*")
                    .type_("Skeleton3D")
                    .owned(false)
                    .done();
                if skeletons.len() > 1 {
                    return Err(format!("{path} contains multiple Skeleton3D nodes; export one rig per GLB."));
                }
                let rig = skeletons.get(0).map(|v| v.cast::<Skeleton3D>());
                let mut bones = Vec::new();
                let mut inverse_rest = Vec::new();
                if let Some(skeleton) = &rig {
                    for i in 0..skeleton.get_bone_count() {
                        bones.push(skeleton.get_bone_name(i).to_string());
                        inverse_rest.push(skeleton.get_bone_global_rest(i).affine_inverse());
                    }
                }
                let url = format!("/model/{}", actors.len());
                let name = model.get_path().to_string();
                if model.is_in_group("gateway_player") {
                    motion = json!({"actor": name, "hz": Engine::singleton().get_physics_ticks_per_second()});
                }
                models.push(json!({"name":name,"asset":asset,"source":path.trim_start_matches("res://"),"url":url,"bones":bones}));
                actors.push(Actor { root:model, rig, inverse_rest });
                assets.insert(url, (file, "model/gltf-binary"));
            } else if let Ok(mesh) = node.clone().try_cast::<MeshInstance3D>() {
                if let Some(resource) = mesh.get_mesh() {
                    if let Ok(plane) = resource.clone().try_cast::<PlaneMesh>() {
                        kinds.push("plane");
                        primitives.push(Primitive {
                            node: mesh,
                            shape: Shape::Plane(plane),
                        });
                    } else if let Ok(cube) = resource.try_cast::<BoxMesh>() {
                        kinds.push("box");
                        primitives.push(Primitive {
                            node: mesh,
                            shape: Shape::Box(cube),
                        });
                    }
                }
            } else if let Ok(light) = node.clone().try_cast::<DirectionalLight3D>() {
                suns.push(light);
            } else if let Ok(lamp) = node.clone().try_cast::<OmniLight3D>() {
                lamps.push(lamp);
            } else if let Ok(world) = node.try_cast::<WorldEnvironment>() {
                environment = Some(world);
            }
        }
        for (url, file, mime) in [
            ("/", "index.html", "text/html; charset=utf-8"),
            ("/gateway.js", "gateway.js", "text/javascript"),
            ("/game.css", "game.css", "text/css"),
            ("/THREE-LICENSE.txt", "THREE-LICENSE.txt", "text/plain"),
        ] {
            assets.insert(
                url.into(),
                (local_path(&format!("res://addons/three_gateway/view/{file}")), mime),
            );
        }
        let actor_words: usize = actors.iter().map(|a| 17 + 12 * a.inverse_rest.len()).sum();
        let bytes =
            20 + 4 * (39 + 26 * primitives.len() + 9 * suns.len() + 8 * lamps.len() + actor_words);
        let manifest = json!({"session":session,"renderer":"headless","bridge":"rust",
            "models":models,"stream":{"version":1,"bytes":bytes,
            "motion":motion,"meshes":kinds,"lights":suns.len(),"lamps":lamps.len()}});
        let world = Self {
            viewport,
            environment,
            primitives,
            suns,
            lamps,
            actors,
            bytes,
        };
        Ok((world, manifest.to_string().into_bytes(), assets))
    }

    pub fn capture(&self, sequence: u32, tick: u32) -> Option<Vec<u8>> {
        let camera = self.viewport.get_camera_3d()?;
        let env = self.environment.as_ref().and_then(|world| world.get_environment());
        let size = self.viewport.get_visible_rect().size;
        let mut p = Packet(Vec::with_capacity(self.bytes));
        for word in [0x31505347, sequence, tick, size.x as u32, size.y as u32] {
            p.0.extend_from_slice(&word.to_le_bytes());
        }
        p.matrix(camera.get_camera_transform().into());
        p.matrix(camera.get_camera_projection());
        p.rgb(env.as_ref().map_or(Color::from_rgb(0.18,0.20,0.24), |e| e.get_bg_color()));
        p.rgb(env.as_ref().map_or(Color::WHITE, |e| e.get_ambient_light_color()));
        p.float(env.as_ref().map_or(0.4, |e| e.get_ambient_light_energy()));
        for primitive in &self.primitives {
            let mesh = &primitive.node;
            let size = match &primitive.shape {
                Shape::Plane(plane) => {
                    let s = plane.get_size();
                    Vector3::new(s.x, 1., s.y)
                }
                Shape::Box(cube) => cube.get_size(),
            };
            let mat = mesh.get_active_material(0).and_then(|m| m.try_cast::<StandardMaterial3D>().ok());
            p.vector(size);
            p.matrix(mesh.get_global_transform().into());
            p.rgb(mat.as_ref().map_or(Color::WHITE, |m| m.get_albedo()));
            p.float(mat.as_ref().map_or(0.0, |m| m.get_metallic()));
            p.float(mat.as_ref().map_or(1.0, |m| m.get_roughness()));
            p.flag(mesh.is_visible_in_tree());
            p.flag(mesh.get_cast_shadows_setting() != ShadowCastingSetting::OFF);
        }
        for light in &self.suns {
            p.vector(-light.get_global_basis().col_c().normalized());
            p.rgb(light.get_color());
            p.float(light.get_param(Param::ENERGY));
            p.flag(light.has_shadow());
            p.flag(light.is_visible_in_tree());
        }
        for lamp in &self.lamps {
            p.vector(lamp.get_global_position());
            p.rgb(lamp.get_color());
            p.float(lamp.get_param(Param::ENERGY));
            p.float(lamp.get_param(Param::RANGE));
        }
        for actor in &self.actors {
            let root = actor.root.get_global_transform();
            p.matrix(root.into());
            p.flag(actor.root.is_visible_in_tree());
            let Some(rig) = &actor.rig else { continue; };
            let to_model = root.affine_inverse() * rig.get_global_transform();
            let to_skeleton = to_model.affine_inverse();
            for (idx, rest) in actor.inverse_rest.iter().enumerate() {
                let bone =
                    to_model * rig.get_bone_global_pose(idx as i32) * *rest * to_skeleton;
                p.vector(bone.basis.col_a());
                p.vector(bone.basis.col_b());
                p.vector(bone.basis.col_c());
                p.vector(bone.origin);
            }
        }
        debug_assert_eq!(p.0.len(), self.bytes);
        Some(p.0)
    }
}

fn matrix(projection: Projection) -> [f32; 16] {
    let [a, b, c, d] = projection.cols;
    [
        a.x, a.y, a.z, a.w, b.x, b.y, b.z, b.w, c.x, c.y, c.z, c.w, d.x, d.y, d.z, d.w,
    ]
}

struct Packet(Vec<u8>);
impl Packet {
    fn float(&mut self, v: f32) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn vector(&mut self, v: Vector3) {
        self.float(v.x);
        self.float(v.y);
        self.float(v.z);
    }
    fn rgb(&mut self, v: Color) {
        self.float(v.r);
        self.float(v.g);
        self.float(v.b);
    }
    fn flag(&mut self, v: bool) {
        self.float(u8::from(v) as f32);
    }
    fn matrix(&mut self, v: Projection) {
        for n in matrix(v) {
            self.float(n);
        }
    }
}
