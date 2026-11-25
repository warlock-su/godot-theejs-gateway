import {Matrix4, Vector3} from 'three';

// Buffer approximately one physics tick. Camera, player root and joints share a single playhead.
export function createPlayerMotion(actor, camera, hz) {
  const stepMs = 1000 / hz;
  const bones = new Set(actor.bones.map(j => j.obj));
  const nodes = [], parentIndex = [], index = new Map();
  actor.root.traverse(node => {
    if (!bones.has(node)) return;
    let parent = node.parent;
    while (parent && !index.has(parent)) parent = parent.parent;
    parentIndex.push(parent ? index.get(parent) : -1);
    index.set(node, nodes.length);
    nodes.push(node);
  });
  const trs = () => ({p:new Vector3(), q:camera.quaternion.clone(), s:new Vector3()});
  const pool = Array.from({length:4}, () => ({
    tick:0, camera:trs(), root:trs(), bones:nodes.map(trs)
  }));
  const history = [], scratch = trs(), local = new Matrix4(), inverse = new Matrix4();
  let cursor = 0, lastDraw = 0, arrival = 0;

  function read(matrix, t) { matrix.decompose(t.p, t.q, t.s); }
  function blend(a, b, weight, matrix) {
    scratch.p.lerpVectors(a.p, b.p, weight);
    scratch.q.slerpQuaternions(a.q, b.q, weight);
    scratch.s.lerpVectors(a.s, b.s, weight);
    matrix.compose(scratch.p, scratch.q, scratch.s);
  }
  function clear() {
    pool.push(...history);
    history.length = 0;
  }
  function push(tick, now) {
    const last = history.at(-1);
    if (last && tick === last.tick) return;
    if (last && (tick < last.tick || tick-last.tick > 5 || now-arrival > 150 ||
        scratch.p.setFromMatrixPosition(actor.root.matrix).distanceToSquared(last.root.p) > 4)) clear();
    if (!history.length) { cursor = tick-1; lastDraw = now; }
    const pose = pool.pop() ?? history.shift();
    pose.tick = tick;
    read(camera.matrix, pose.camera);
    read(actor.root.matrix, pose.root);
    for (let i=0; i<nodes.length; i++) {
      const parent = parentIndex[i];
      inverse.copy(parent < 0 ? actor.root.matrix : nodes[parent].matrixWorld).invert();
      read(local.multiplyMatrices(inverse, nodes[i].matrixWorld), pose.bones[i]);
    }
    history.push(pose);
    arrival = now;
  }
  function present(now) {
    const newest = history.at(-1);
    if (!newest) return;
    // Correct clock drift gradually; packet arrival jitter must not move the playhead backwards.
    const elapsed = (now-lastDraw)/stepMs;
    lastDraw = now;
    const target = newest.tick + (now-arrival)/stepMs - 1.25;
    const rate = Math.max(0.9, Math.min(1.1, 1 + 0.075*(target-cursor)));
    cursor = Math.min(newest.tick, cursor + elapsed*rate);
    const first = history[0];
    if (history.length === 1) return;
    cursor = Math.max(first.tick, cursor);
    let i=1;
    while (i<history.length-1 && history[i].tick < cursor) i++;
    const a=history[i-1], b=history[i], weight=(cursor-a.tick)/(b.tick-a.tick);
    blend(a.camera, b.camera, weight, camera.matrix);
    camera.matrixWorldNeedsUpdate = true;
    camera.updateMatrixWorld(true);
    blend(a.root, b.root, weight, actor.root.matrix);
    actor.root.matrixWorldNeedsUpdate = true;
    for (let j=0; j<nodes.length; j++) {
      blend(a.bones[j], b.bones[j], weight, local);
      const parent = parentIndex[j];
      nodes[j].matrixWorld.multiplyMatrices(parent < 0 ? actor.root.matrix : nodes[parent].matrixWorld, local);
    }
  }
  return {push, present, clear};
}
