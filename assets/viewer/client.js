import {prepareView} from './viewer.js';
import {openPoseStream} from './poses.js';

const get = id => document.getElementById(id);
const status = get('status');
const mobile = matchMedia('(any-pointer:coarse)').matches;
const wasm = document.documentElement.dataset.backend==='wasm';
let engine, inputSocket, poseSocket, generation=0;
let packet, fresh=false, view, mask=0, jumpEdge=0;
let startTime=0, frames=0, gameReady=false, transformOffset=null;
const size={width:1,height:1};
function resize() {
  const ratio=Math.min(devicePixelRatio,mobile?1.5:1);
  size.width=Math.max(1,Math.round(innerWidth*ratio));
  size.height=Math.max(1,Math.round(innerHeight*ratio));
}
resize(); addEventListener('resize',resize);

function fail(error) {
  status.hidden=false;
  status.textContent='Gateway · '+(error.message || error);
  console.error(error);
}
async function configure(scene) {
    const requested=++generation;
    view?.dispose();
    view=null;packet=null;fresh=false;gameReady=false;frames=0;status.hidden=false;
    const stream=scene.stream;
    let offset=39+26*stream.meshes.length+9*stream.lights+8*stream.lamps;
    transformOffset=stream.meshes.length ? 39+3 : null;
    for (const actor of scene.models) {
      if (actor.name===stream.motion?.actor || transformOffset===null) {transformOffset=offset;break;}
      offset+=17+12*actor.bones.length;
    }
    if(wasm) for(const model of scene.models) {
      model.url=new URL('models/'+model.source.split('/').map(encodeURIComponent).join('/'),document.baseURI).href;
    }
    status.textContent='Loading scene…';
    const next=await prepareView(scene);
    if(requested===generation) view=next;
    else next.dispose();
}
window.threeGame={
  configure(text) {configure(JSON.parse(text)).catch(fail);},
  publish(pointer,length) {
    if(!packet || packet.length!==length) packet=new Uint8Array(length);
    packet.set(engine.rtenv.HEAPU8.subarray(Number(pointer),Number(pointer)+Number(length)));
    fresh=true;
  },
  takeKeys() {const result=mask | jumpEdge;jumpEdge=0;return result;},
  snapshot() {
    if(!packet || !gameReady) return null;
    return {tick:new DataView(packet.buffer).getUint32(8,true),
      position:transformOffset===null?null:[...new Float32Array(packet.buffer,20+4*(transformOffset+12),3)],
      backend:wasm?'wasm':'native',size:[size.width,size.height]};
  }
};
function render(now) {
  if(view && packet && !document.hidden) {
    view.draw(fresh?packet.buffer:null,performance.now(),size);
    fresh=false;
    if(!gameReady) {gameReady=true;status.hidden=true;startTime=performance.now();}
    else {
      frames++;
      if(now-startTime>=500) {
        get('fps').textContent=Math.round(frames*1000/(now-startTime))+' FPS';
        frames=0;startTime=now;
      }
    }
  }
  requestAnimationFrame(render);
}

const keyBits={KeyA:1,ArrowLeft:1,KeyD:2,ArrowRight:2,KeyW:4,ArrowUp:4,KeyS:8,ArrowDown:8,Space:16};
const held=new Set();
const stick=get('stick'), knob=stick.firstElementChild, jump=get('jump');
let stickId=null, jumpId=null, direction=0;
function update() {
  let next=direction | (jumpId===null?0:16);
  for(const key of held)next|=keyBits[key];
  jumpEdge|=next & ~mask & 16;
  if(next!==mask && inputSocket?.readyState===WebSocket.OPEN) inputSocket.send(Uint8Array.of(next));
  mask=next;
}
function key(event) {
  if(!keyBits[event.code]||event.ctrlKey||event.altKey||event.metaKey)return;
  event.preventDefault();
  if(event.type==='keydown') held.add(event.code); else held.delete(event.code);
  update();
}
addEventListener('keydown',key);addEventListener('keyup',key);
function move(event) {
  if(event.pointerId!==stickId)return;
  const r=stick.getBoundingClientRect(),x=event.clientX-r.left-r.width/2,y=event.clientY-r.top-r.height/2;
  const dist=Math.hypot(x,y),limit=r.width*.3,scale=Math.min(1,limit/(dist||1));
  knob.style.transform='translate('+x*scale+'px,'+y*scale+'px)';
  direction=0;
  if(dist>r.width*.12){
    if(Math.abs(x)>dist*.38)direction|=x<0?1:2;
    if(Math.abs(y)>dist*.38)direction|=y<0?4:8;
  }
  update();
}
stick.onpointerdown=e=>{if(stickId===null){stickId=e.pointerId;stick.setPointerCapture(stickId);move(e);}};
stick.onpointermove=move;
stick.onpointerup=stick.onpointercancel=stick.onlostpointercapture=e=>{
  if(e.pointerId===stickId){stickId=null;direction=0;knob.style.transform='';update();}
};
jump.onpointerdown=e=>{if(jumpId===null){jumpId=e.pointerId;jump.setPointerCapture(jumpId);jump.classList.add('pressed');update();}};
jump.onpointerup=jump.onpointercancel=jump.onlostpointercapture=e=>{
  if(e.pointerId===jumpId){jumpId=null;jump.classList.remove('pressed');update();}
};
function reset() {held.clear();direction=0;stickId=jumpId=null;update();jumpEdge=0;knob.style.transform='';jump.classList.remove('pressed');}
addEventListener('blur',reset);
document.addEventListener('visibilitychange',()=>{reset();view?.reset();startTime=performance.now();frames=0;});
const full=get('fullscreen'),root=document.documentElement;
const fullscreen=()=>document.fullscreenElement||document.webkitFullscreenElement;
full.onclick=async()=>{
  try {
    if(fullscreen()) await (document.exitFullscreen||document.webkitExitFullscreen).call(document);
    else if(root.requestFullscreen||root.webkitRequestFullscreen) await (root.requestFullscreen||root.webkitRequestFullscreen).call(root);
    else throw new Error();
  } catch {
    const hint=get('hint');hint.hidden=false;hint.textContent='Fullscreen is unavailable in this browser.';
    setTimeout(()=>{hint.hidden=true;},7000);
  }
};
function fullLabel(){ full.textContent=fullscreen()?'Exit fullscreen':'Fullscreen';resize();}
document.addEventListener('fullscreenchange',fullLabel);document.addEventListener('webkitfullscreenchange',fullLabel);
if(matchMedia('(display-mode:standalone)').matches || navigator.standalone)full.hidden=true;
requestAnimationFrame(render);
async function startNative(){
  const response=await fetch('/scene',{cache:'no-store'});
  if(!response.ok) throw Error('Manifest HTTP '+response.status);
  const manifest=await response.json();
  await configure(manifest);
  const url=new URL('/input',location.href);
  url.protocol='ws:'; url.searchParams.set('session',manifest.session);
  inputSocket=new WebSocket(url);
  inputSocket.onopen=()=>inputSocket.send(Uint8Array.of(mask));
  inputSocket.onclose=()=>{if(poseSocket) poseSocket.close();};
  poseSocket=openPoseStream(manifest,buffer=>{packet=new Uint8Array(buffer);fresh=true;},()=>{
    status.hidden=false;status.textContent='Reconnecting…';
    setTimeout(()=>location.reload(),450);
  });
}
if(wasm) {
  engine=new Engine({executable:'game',gdextensionLibs:['godot_three_gateway.wasm'],persistentPaths:[],
    canvas:get('simulation'),canvasResizePolicy:0,focusCanvas:false,
    args:['--headless','--disable-render-loop','--max-fps','60','--audio-driver','Dummy',
      '--','--gateway-scene='+document.documentElement.dataset.scene]});
  engine.startGame({onExit:code=>{if(code)fail(Error('Godot exit '+code));}}).catch(fail);
} else startNative().catch(fail);
