use std::collections::{BTreeMap, HashMap};
use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use axum::Router;
use axum::body::{Body, Bytes};
use axum::extract::ws::{Message, WebSocket};
use axum::extract::{OriginalUri, Query, State, WebSocketUpgrade};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use serde::Deserialize;
use tokio::sync::{oneshot, watch};
use tokio_util::io::ReaderStream;

pub type Assets = HashMap<String, (PathBuf, &'static str)>;

#[derive(Default)]
struct Keys {
    held: u8,
    jump_edge: u8,
}

#[derive(Clone)]
struct App(Arc<Shared>);
struct Shared {
    assets: Assets,
    manifest: Bytes,
    session: String,
    poses: watch::Sender<Bytes>,
    keys: Mutex<BTreeMap<u64, Keys>>,
    next_client: AtomicU64,
}

pub struct Server {
    app: App,
    stop: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
}

impl Server {
    pub fn start(
        port: u16,
        session: String,
        manifest: Vec<u8>,
        assets: Assets,
    ) -> std::io::Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", port))?;
        listener.set_nonblocking(true)?;
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()?;
        let (stop, stopped) = oneshot::channel();
        let app = App(Arc::new(Shared {
            assets,
            manifest: manifest.into(),
            session,
            poses: watch::channel(Bytes::new()).0,
            keys: Mutex::default(),
            next_client: AtomicU64::new(0),
        }));
        let routes = Router::new()
            .route("/scene", get(scene))
            .route("/poses", get(upgrade))
            .route("/input", get(upgrade))
            .fallback(get(asset))
            .with_state(app.clone());
        let thread = std::thread::Builder::new()
            .name("three-rust-http".into())
            .spawn(move || {
                runtime.block_on(async move {
                    let listener = tokio::net::TcpListener::from_std(listener)
                        .expect("bound loopback listener");
                    tokio::select! {
                        result = axum::serve(listener, routes).into_future() => {
                            if let Err(error) = result { eprintln!("Rust bridge HTTP: {error}"); }
                        }
                        _ = stopped => {}
                    }
                });
            })?;
        Ok(Self {
            app,
            stop: Some(stop),
            thread: Some(thread),
        })
    }

    pub fn subscribed(&self) -> bool {
        self.app.0.poses.receiver_count() != 0
    }
    pub fn publish(&self, bytes: Vec<u8>) {
        let _ = self.app.0.poses.send(bytes.into());
    }
    pub fn keys(&self) -> u8 {
        let mut keys = self.app.0.keys.lock().unwrap();
        keys.values_mut().fold(0, |mask, client| {
            mask | client.held | std::mem::take(&mut client.jump_edge)
        })
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

async fn scene(State(app): State<App>) -> impl IntoResponse {
    (
        [
            (header::CONTENT_TYPE, "application/json"),
            (header::CACHE_CONTROL, "no-store"),
        ],
        app.0.manifest.clone(),
    )
}

async fn asset(State(app): State<App>, OriginalUri(uri): OriginalUri) -> Response {
    let Some((path, mime)) = app.0.assets.get(uri.path()) else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let Ok(file) = tokio::fs::File::open(path).await else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let mut builder = Response::builder()
        .header(header::CONTENT_TYPE, *mime)
        .header(header::CACHE_CONTROL, "no-store");
    if let Ok(meta) = file.metadata().await {
        builder = builder.header(header::CONTENT_LENGTH, meta.len());
    }
    builder
        .body(Body::from_stream(ReaderStream::new(file)))
        .unwrap()
}

#[derive(Deserialize)]
struct Session {
    session: String,
}

async fn upgrade(
    State(app): State<App>,
    OriginalUri(uri): OriginalUri,
    Query(query): Query<Session>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> Response {
    if query.session != app.0.session {
        return StatusCode::CONFLICT.into_response();
    }
    if let Some(origin) = headers.get(header::ORIGIN) {
        let host = headers
            .get(header::HOST)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        if origin.to_str().ok() != Some(format!("http://{host}").as_str()) {
            return StatusCode::FORBIDDEN.into_response();
        }
    }
    let input = uri.path() == "/input";
    ws.max_message_size(64)
        .max_frame_size(128)
        .on_upgrade(move |socket| async move {
            if input {
                receive_keys(socket, app).await;
            } else {
                send_poses(socket, app.0.poses.subscribe()).await;
            }
        })
}

async fn receive_keys(mut socket: WebSocket, app: App) {
    let id = app.0.next_client.fetch_add(1, Ordering::Relaxed);
    while let Some(Ok(message)) = socket.recv().await {
        match message {
            Message::Binary(data) if data.len() == 1 && data[0] < 32 => {
                let mask = data[0];
                let mut keys = app.0.keys.lock().unwrap();
                let client = keys.entry(id).or_default();
                client.jump_edge |= mask & !client.held & 16;
                client.held = mask;
            }
            Message::Ping(_) | Message::Pong(_) => continue,
            _ => break,
        }
    }
    app.0.keys.lock().unwrap().remove(&id);
}

async fn send_poses(mut socket: WebSocket, mut poses: watch::Receiver<Bytes>) {
    while poses.changed().await.is_ok() {
        let latest = poses.borrow_and_update().clone();
        if socket.send(Message::Binary(latest)).await.is_err() {
            return;
        }
        loop {
            match socket.recv().await {
                Some(Ok(Message::Binary(ack))) if ack.as_ref() == [1] => break,
                Some(Ok(Message::Ping(_) | Message::Pong(_))) => continue,
                _ => return,
            }
        }
    }
}
