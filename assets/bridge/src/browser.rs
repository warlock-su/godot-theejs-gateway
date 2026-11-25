use godot::classes::{Engine, Object};
use godot::prelude::*;
use std::{cell::RefCell, collections::HashMap, io, path::PathBuf};

pub type Assets = HashMap<String, (PathBuf, &'static str)>;

// JavaScript copies each packet synchronously while the Rust allocation is alive.
pub struct Server(RefCell<Gd<Object>>);

impl Server {
    pub fn start(_: u16, _: String, manifest: Vec<u8>, _: Assets) -> io::Result<Self> {
        let mut bridge = Engine::singleton().get_singleton("JavaScriptBridge")
            .ok_or_else(|| io::Error::other("JavaScriptBridge unavailable"))?;
        let mut host = bridge.call("get_interface", &["threeGame".to_variant()])
            .try_to::<Gd<Object>>().map_err(|_| io::Error::other("Missing threeGame on page"))?;
        let manifest = String::from_utf8(manifest).map_err(io::Error::other)?;
        host.call("configure", &[manifest.to_variant()]);
        Ok(Self(RefCell::new(host)))
    }
    pub fn subscribed(&self) -> bool { true }
    pub fn keys(&self) -> u8 { self.0.borrow_mut().call("takeKeys", &[]).to::<i64>() as u8 }
    pub fn publish(&self, bytes: Vec<u8>) {
        self.0.borrow_mut().call("publish", &[(bytes.as_ptr() as i64).to_variant(), (bytes.len() as i64).to_variant()]);
    }
}
