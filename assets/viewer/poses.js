const MAGIC = 0x31505347;
const receipt = new Uint8Array([1]);

// Vectors share one reusable block. The affine bone matrices omit the fixed row [0,0,0,1].
export function createPoseDecoder(manifest) {
  const layout = manifest.stream;
  if (layout.version !== 1) throw new Error('Неизвестный формат поз');
  const values = new Float32Array((layout.bytes - 20) / 4);
  let offset = 0;
  const scalars = [];
  function vector(size) {
    const slice = values.subarray(offset, offset + size);
    offset += size;
    return slice;
  }
  function scalar(target, key, flag = false) {
    scalars.push({target, key, flag, offset: offset++});
  }
  const state = {camera: vector(16), projection: vector(16), background: vector(3), ambient: vector(3)};
  scalar(state, 'ambientEnergy');
  state.meshes = layout.meshes.map(kind => {
    const mesh = {kind, size: vector(3), matrix: vector(16), color: vector(3)};
    scalar(mesh, 'metallic'); scalar(mesh, 'roughness'); scalar(mesh, 'visible', true); scalar(mesh, 'shadow', true);
    return mesh;
  });
  state.lights = Array.from({length: layout.lights}, () => {
    const light = {direction: vector(3), color: vector(3)};
    scalar(light, 'energy'); scalar(light, 'shadow', true); scalar(light, 'visible', true);
    return light;
  });
  state.lamps = Array.from({length: layout.lamps}, () => {
    const lamp = {position: vector(3), color: vector(3)};
    scalar(lamp, 'energy'); scalar(lamp, 'range');
    return lamp;
  });
  state.models = manifest.models.map(model => {
    const actor = {matrix: vector(16)};
    scalar(actor, 'visible', true);
    actor.affineBones = vector(12 * model.bones.length);
    return actor;
  });
  if (offset !== values.length) throw new Error('Некорректная длина описания сцены');
  return packet => {
    const header = new DataView(packet, 0, 20);
    if (packet.byteLength !== layout.bytes || header.getUint32(0, true) !== MAGIC)
      throw new Error('Некорректный пакет позы');
    state.frame = header.getUint32(4, true);
    state.pose = header.getUint32(8, true);
    state.width = header.getUint32(12, true);
    state.height = header.getUint32(16, true);
    values.set(new Float32Array(packet, 20));
    for (const {target, key, flag, offset} of scalars)
      target[key] = flag ? values[offset] !== 0 : values[offset];
    return state;
  };
}

export function openPoseStream(manifest, onPose, onClose) {
  const url = new URL('/poses', location.href);
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('session', manifest.session);
  const socket = new WebSocket(url);
  socket.binaryType = 'arraybuffer';
  socket.onmessage = ({data}) => {
    if (socket.readyState !== WebSocket.OPEN) return;
    if (!(data instanceof ArrayBuffer) || data.byteLength !== manifest.stream.bytes) {
      socket.close(4000, 'Invalid pose size');
      return;
    }
    onPose(data);
    socket.send(receipt);
  };
  socket.onclose = onClose;
  return socket;
}
