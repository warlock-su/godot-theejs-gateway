import * as T from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {createPoseDecoder} from './poses.js';
import {createPlayerMotion} from './motion.js';

export async function prepareView(manifest) {
  const renderer = new T.WebGLRenderer({canvas:document.querySelector('#webgl'), antialias:false});
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFShadowMap;
  const scene = new T.Scene(), camera = new T.PerspectiveCamera(), ambient = new T.AmbientLight();
  scene.background = new T.Color();
  scene.add(ambient);
  camera.matrixAutoUpdate = false;
  const loader = new GLTFLoader();
  const actors = await Promise.all(manifest.models.map(async model => {
    const {scene:root} = await loader.loadAsync(model.url);
    root.updateMatrixWorld(true);
    const joints = new Map();
    root.traverse(obj => {
      if (obj.isBone) {
        joints.set(obj.name,{obj,bind:obj.matrixWorld.clone()});
        obj.matrixWorldAutoUpdate = false;
      }
      if (obj.isMesh) obj.castShadow = obj.receiveShadow = true;
      if (obj.isSkinnedMesh) obj.frustumCulled = false;
    });
    const bones = model.bones.map(name => {
      if (!joints.has(name)) throw Error(model.source+' · Missing bone '+name);
      return joints.get(name);
    });
    root.matrixAutoUpdate = false;
    scene.add(root);
    return {root,bones};
  }));
  const meshes = manifest.stream.meshes.map(kind => {
    const geometry = kind==='box' ? new T.BoxGeometry() : new T.PlaneGeometry().rotateX(-Math.PI/2);
    const mesh = new T.Mesh(geometry,new T.MeshStandardMaterial());
    mesh.matrixAutoUpdate = false;
    mesh.receiveShadow = true;
    scene.add(mesh);
    return mesh;
  });
  const suns = Array.from({length:manifest.stream.lights}, () => {
    const sun = new T.DirectionalLight();
    sun.shadow.mapSize.set(2048,2048);
    Object.assign(sun.shadow.camera,{left:-12,right:12,top:12,bottom:-12,near:.1,far:64});
    sun.shadow.camera.updateProjectionMatrix();
    sun.shadow.normalBias = .009;
    scene.add(sun,sun.target);
    return sun;
  });
  const lamps = Array.from({length:manifest.stream.lamps}, () => {
    const light = new T.PointLight();
    scene.add(light);
    return light;
  });
  const decode = createPoseDecoder(manifest), clock = manifest.stream.motion;
  const motion = clock && createPlayerMotion(actors[manifest.models.findIndex(a=>a.name===clock.actor)],camera,clock.hz);
  const delta = new T.Matrix4(), scale = new T.Matrix4(), direction = new T.Vector3();
  const color = (out, rgb) => out.setRGB(...rgb,T.SRGBColorSpace);
  function apply(pose,size) {
    if (renderer.domElement.width!==size.width || renderer.domElement.height!==size.height)
      renderer.setSize(size.width,size.height,false);
    camera.matrix.fromArray(pose.camera);
    camera.matrixWorldNeedsUpdate=true;
    camera.updateMatrixWorld(true);
    camera.projectionMatrix.fromArray(pose.projection);
    camera.projectionMatrix.elements[0] *= (pose.width/pose.height)/(size.width/size.height);
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
    color(scene.background,pose.background);
    color(ambient.color,pose.ambient);
    ambient.intensity=pose.ambientEnergy*Math.PI;
    pose.meshes.forEach((p,i)=>{
      const mesh=meshes[i];
      mesh.matrix.fromArray(p.matrix).multiply(scale.makeScale(...p.size));
      mesh.matrixWorldNeedsUpdate=true;
      mesh.visible=p.visible; mesh.castShadow=p.shadow;
      color(mesh.material.color,p.color);
      mesh.material.metalness=p.metallic; mesh.material.roughness=p.roughness;
    });
    pose.lights.forEach((p,i)=>{
      const sun=suns[i];
      sun.target.position.setFromMatrixPosition(camera.matrix).addScaledVector(camera.getWorldDirection(direction),6);
      sun.position.copy(sun.target.position).addScaledVector(direction.fromArray(p.direction),-24);
      color(sun.color,p.color);
      sun.intensity=p.energy*Math.PI; sun.castShadow=p.shadow; sun.visible=p.visible;
    });
    pose.lamps.forEach((p,i)=>{
      const lamp=lamps[i];
      lamp.position.fromArray(p.position); color(lamp.color,p.color);
      lamp.intensity=p.energy*Math.PI; lamp.distance=p.range;
    });
    pose.models.forEach((p,i)=>{
      const {root,bones}=actors[i];
      root.visible=p.visible; root.matrix.fromArray(p.matrix); root.matrixWorldNeedsUpdate=true;
      const a=p.affineBones;
      bones.forEach(({obj,bind},j)=>{
        const k=12*j;
        delta.set(a[k],a[k+3],a[k+6],a[k+9],a[k+1],a[k+4],a[k+7],a[k+10],
          a[k+2],a[k+5],a[k+8],a[k+11],0,0,0,1);
        obj.matrixWorld.copy(root.matrix).multiply(delta).multiply(bind);
      });
    });
  }
  return {
    draw(packet,now,size) {
      if(packet) {
        const pose=decode(packet);
        apply(pose,size);
        motion?.push(pose.pose,now);
      }
      motion?.present(now);
      renderer.render(scene,camera);
    },
    reset(){motion?.clear();},
    dispose(){
      const resources=new Set();
      scene.traverse(node=>{
        if(node.geometry) resources.add(node.geometry);
        if(node.skeleton) resources.add(node.skeleton);
        for(const mat of [].concat(node.material||[])){
          resources.add(mat);
          for(const value of Object.values(mat)) if(value?.isTexture) resources.add(value);
        }
        if(node.shadow) resources.add(node.shadow);
      });
      for(const item of resources) item.dispose();
      renderer.dispose();
    }
  };
}
