/**
 * The house as its own scene. The map shows where a building is, and this shows what reaches it.
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { flow, ring, type Flow } from "./flow";

export const MODES = ["landline", "cellular", "satellite"] as const;
export type Mode = (typeof MODES)[number];

export type Scene = {
  setMode: (next: Mode) => void;
  setColour: (next: string) => void;
  setSpeed: (next: number) => void;
  setStill: (next: boolean) => void;
  stop: () => void;
};

export type SceneOptions = {
  readonly colour?: string;
  readonly mbps?: number;
  readonly mode?: Mode;
  readonly still?: boolean;
  /**
   * Whether the house stands on its own lit plate. In a 232 px band the plate is the ground.
   * Given a quarter of the screen it turns into a lit rectangle and the house looks framed.
   * Off, the soft shadow falls on whatever is behind the canvas.
   */
  readonly grounded?: boolean;
};

const WALL = 0x1a1e26;
const ROOF = 0x0f1218;
const TRIM = 0x2b323d;

/** Where the signal comes from, and what the house does with it. */
const SHAPE = {
  landline: { open: 0, router: 0, dish: 0, route: 'ground' },
  cellular: { open: 1, router: 1, dish: 0, route: 'air' },
  satellite: { open: 0, router: 0, dish: 1, route: 'sky' },
};

/** Busier and quicker on a faster line, so you see the speed without reading a number. */
function traffic(mbps: number): { speed: number; density: number } {
  const k = Math.min(1, Math.log10(Math.max(mbps, 10) / 10) / Math.log10(300));
  return { speed: 0.12 + k * 0.5, density: 1.4 + k * 5.5 };
}

export function house3d(canvas: HTMLCanvasElement, options: SceneOptions = {}): Scene {
  let colour = options.colour ?? '#38bdf8';
  let mbps = options.mbps ?? 1000;
  let mode = options.mode ?? 'landline';
  let previous = mode;
  let changedAt = -1e9;
  let still = options.still ?? false;
  let raf = 0;
  const clock = new THREE.Clock();

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.26;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 400);

  // key light front left, rim from behind right (the rim is what picks out the bevels)
  const key = new THREE.DirectionalLight(0xdfe8ff, 1.35);
  key.position.set(5, 7, 6);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xbcd2ff, 1.35);
  rim.position.set(-6, 4, -6);
  scene.add(rim);
  scene.add(new THREE.AmbientLight(0x6f7f96, 0.3));

  const house = new THREE.Group();
  scene.add(house);

  /** A bevelled slab from a flat outline. */
  function slab(
    shape: THREE.Shape,
    depth: number,
    bevel: number,
    material: THREE.Material,
  ): THREE.Mesh {
    const geometry = new THREE.ExtrudeGeometry(shape, {
      depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel,
      bevelSegments: 3, curveSegments: 4,
    });
    geometry.center();
    return new THREE.Mesh(geometry, material);
  }

  const wallMat = new THREE.MeshStandardMaterial({ color: WALL, roughness: 0.62, metalness: 0.08 });
  const roofMat = new THREE.MeshStandardMaterial({ color: ROOF, roughness: 0.5, metalness: 0.12 });
  const trimMat = new THREE.MeshStandardMaterial({ color: TRIM, roughness: 0.4, metalness: 0.2 });

  const W = 3.2, H = 2.3, D = 2.8;

  const bodyShape = new THREE.Shape();
  bodyShape.moveTo(-W / 2, 0); bodyShape.lineTo(W / 2, 0);
  bodyShape.lineTo(W / 2, H); bodyShape.lineTo(-W / 2, H);
  bodyShape.closePath();
  const body = slab(bodyShape, D, 0.05, wallMat);
  body.position.set(0, H / 2, 0);
  body.rotation.x = 0;
  house.add(body);

  // overhang, since a roof flush with the walls looks like a primitive
  const roofShape = new THREE.Shape();
  roofShape.moveTo(-W / 2 - 0.22, 0);
  roofShape.lineTo(W / 2 + 0.22, 0);
  roofShape.lineTo(0, 1.35);
  roofShape.closePath();
  const roof = slab(roofShape, D + 0.34, 0.05, roofMat);
  house.add(roof);

 // the roof sits on the walls by measurement, not by guess
  function bounds(mesh: THREE.Mesh): THREE.Box3 {
    mesh.geometry.computeBoundingBox();
    return mesh.geometry.boundingBox!;
  }

  const EAVES = body.position.y + bounds(body).max.y;
  roof.position.set(0, EAVES - bounds(roof).min.y, 0);
  const RIDGE = roof.position.y + bounds(roof).max.y;

  // emissive windows: the only warm light on the house, and they give the walls scale
  const glass = new THREE.MeshStandardMaterial({
    color: 0x0a0c10, emissive: new THREE.Color(0xffd9a0), emissiveIntensity: 0.9,
    roughness: 0.25, metalness: 0,
  });
  /** Where the wall's front face really is. */
  const FRONT = bounds(body).max.z + 0.03;

  const PANES: readonly (readonly [number, number])[] = [
    [-0.85, 1.35], [0.85, 1.35], [-0.85, 0.5], [0.85, 0.5],
  ];
  for (const [x, y] of PANES) {
    const pane = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.5, 0.06), glass);
    pane.position.set(x, y, FRONT);
    house.add(pane);
  }
  const door = new THREE.Mesh(new THREE.BoxGeometry(0.52, 1.0, 0.08), trimMat);
  door.position.set(0, 0.5, FRONT);
  house.add(door);

  // through the slope, not out of the ridge, and tall enough to clear it
  const chimney = new THREE.Mesh(new THREE.BoxGeometry(0.32, 1.15, 0.32), roofMat);
  chimney.position.set(-0.78, RIDGE - 0.18, -0.45);
  house.add(chimney);

  // router, inside
  const router = new THREE.Group();
  const shell = new THREE.Mesh(
    new THREE.BoxGeometry(0.66, 0.13, 0.44),
    new THREE.MeshStandardMaterial({ color: 0xeef2f8, roughness: 0.3, metalness: 0.1 }),
  );
  router.add(shell);
  for (const side of [-1, 1]) {
    const aerial = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.024, 0.46, 4, 8),
      new THREE.MeshStandardMaterial({ color: 0xeef2f8, roughness: 0.35 }),
    );
    aerial.position.set(side * 0.26, 0.3, -0.14);
    aerial.rotation.z = side * 0.3;
    router.add(aerial);
  }
  router.position.set(0, 1.0, 0);
  house.add(router);

  // dish, on the roof
  const dish = new THREE.Group();
  const BOWL = 0.36;
  const bowl = new THREE.Mesh(
    new THREE.SphereGeometry(BOWL, 28, 18, 0, Math.PI * 2, 0, Math.PI / 2.7),
    new THREE.MeshStandardMaterial({ color: 0xe6ecf5, roughness: 0.35, metalness: 0.15, side: THREE.DoubleSide }),
  );
  bowl.rotation.set(-Math.PI * 0.6, 0, Math.PI * 0.12);
  dish.add(bowl);
  const MAST = 0.6;
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.033, 0.033, MAST, 8), trimMat);
  mast.position.y = -MAST / 2;
  dish.add(mast);
  /** Stands on the slope instead of sinking into it. */
  const DISH_X = 0.86;
  const HALF = W / 2 + 0.22;
  const slope = EAVES + 1.35 * (1 - Math.abs(DISH_X) / HALF);
  // Lifted by the mast plus the bowl's radius. The group's origin is the bowl's centre, so
  // anything less buries the lower rim in the tiles.
  dish.position.set(DISH_X, slope + MAST + BOWL * 0.35, 0.62);
  house.add(dish);

  // A blurred disc under the house in place of a shadow map. At this exposure a real shadow
  // is either invisible or a hard black hole, and a hard-edged one reads as a plate.
  function softDisc(): THREE.CanvasTexture {
    const size = 128;
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const g = c.getContext("2d")!;
    const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    grad.addColorStop(0, 'rgba(0,0,0,0.85)');
    grad.addColorStop(0.55, 'rgba(0,0,0,0.45)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
    return new THREE.CanvasTexture(c);
  }

  const shadow = new THREE.Mesh(
    new THREE.CircleGeometry(3.6, 48).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({
      map: softDisc(), transparent: true, opacity: 0.9, depthWrite: false,
    }),
  );
  shadow.position.y = 0.002;
  scene.add(shadow);

  if (options.grounded ?? true) {
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(300, 64).rotateX(-Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0x07080a, roughness: 1 }),
    );
    scene.add(ground);
  }

  // the three routes, each a tube of flowing light
  const ROUTES: Record<string, Flow> = {
    ground: flow([[-9, 0.06, 0], [-4, 0.06, 0], [-1.2, 0.06, 0], [0, 0.06, 0], [0, 0.9, 0]],
                 { colour, radius: 0.085 }),
    sky: flow([[DISH_X, slope + MAST + BOWL * 0.35, 0.62], [1.5, 5.0, 0.95], [2.5, 8.2, 1.5], [3.5, 11.8, 2.1]],
               { colour, radius: 0.09, steps: 60, fadeIn: 0.02 }),
  };
  for (const r of Object.values(ROUTES)) scene.add(r.mesh);

  // cellular is a broadcast, so it's rings, no tube
  /** Billboarded every frame so they always draw as circles. */
  const rings = Array.from({ length: 4 }, () => {
    const r = ring(colour);
    r.position.set(0, 1.05, 0);
    scene.add(r);
    return r;
  });

  /**
   * Two boxes, since the drawing comes in two sizes. The house and wires fit HOUSE. Cellular's
   * rings grow to a radius of about three around the aerial, and HOUSE cut them off on all four
   * sides. BROADCAST holds them but leaves the house small in the four modes without rings.
   * So the camera holds HOUSE and eases back to BROADCAST as the rings come in, on the same
   * 0 to 1 the walls open on. Centred below the house's middle, since the chimney, aerial and
   * dish all stand above the roof.
   */
  const HOUSE = { height: 5.4, width: 6.4 };
  const BROADCAST = { height: 7.4, width: 8.2 };
  const CENTRE = 1.5;
  const AIM = new THREE.Vector3(0.58, 0.4, 0.92).normalize();

  let sized = { w: 0, h: 0 };
  /** Camera distance for each box at the canvas's current size. */
  let range = { near: 0, far: 0 };

  function resize(): void {
    const box = canvas.getBoundingClientRect();
    if (box.width === sized.w && box.height === sized.h) return;
    sized = { w: box.width, h: box.height };
    renderer.setSize(box.width, box.height, false);
    camera.aspect = box.width / Math.max(1, box.height);
    const vertical = Math.tan((camera.fov * Math.PI) / 360);
    const backFor = (subject: { height: number; width: number }): number =>
      Math.max(
        subject.height / 2 / vertical,
        subject.width / 2 / (vertical * camera.aspect),
      ) * 1.2;
    range = { near: backFor(HOUSE), far: backFor(BROADCAST) };
    camera.updateProjectionMatrix();
  }

  /** Camera position for how much of the broadcast is showing. */
  function watchFrom(air: number): void {
    const back = range.near + (range.far - range.near) * air;
    camera.position.copy(AIM).multiplyScalar(back).add(new THREE.Vector3(0, CENTRE, 0));
    camera.lookAt(0, CENTRE, 0);
  }

  function frame(): void {
    resize();
    const dt = still ? 0.016 : Math.min(0.064, clock.getDelta());
    const now = performance.now();
    const k = Math.min(1, (now - changedAt) / 450);
    const eased = 1 - (1 - k) ** 3;
    const a = SHAPE[previous];
    const b = SHAPE[mode];
    const open = a.open + (b.open - a.open) * eased;
    const flow4 = traffic(mbps);

    // the walls opening drives everything else
    // three caches whether a material needs the transparent pass. Flip the flag without
    // telling it and the walls stay solid at any opacity.
    const clear = open > 0.01;
    if (wallMat.transparent !== clear) {
      wallMat.transparent = clear;
      wallMat.depthWrite = !clear;
      wallMat.needsUpdate = true;
    }
    if (roofMat.transparent !== clear) {
      roofMat.transparent = clear;
      roofMat.depthWrite = !clear;
      roofMat.needsUpdate = true;
    }
    wallMat.opacity = 1 - open * 0.88;
    roofMat.opacity = 1 - open * 0.78;
    glass.emissiveIntensity = 0.9 * (1 - open * 0.8);

    const showRouter = a.router + (b.router - a.router) * eased;
    const showDish = a.dish + (b.dish - a.dish) * eased;
    router.visible = showRouter > 0.02;
    router.scale.setScalar(0.55 + 0.45 * showRouter);
    dish.visible = showDish > 0.02;
    dish.scale.setScalar(0.55 + 0.45 * showDish);

    for (const [name, route] of Object.entries(ROUTES)) {
      const want = (a.route === name ? 1 - eased : 0) + (b.route === name ? eased : 0);
      route.mesh.visible = want > 0.01;
      route.setStrength(1.9 * want);
      route.setTraffic(flow4);
      route.step(dt);
    }

    const air = (a.route === 'air' ? 1 - eased : 0) + (b.route === 'air' ? eased : 0);
    // Before the rings, which face the camera. Move the camera after them and you get a frame
    // of rings facing where it used to be.
    watchFrom(air);

    rings.forEach((r, i) => {
      const paint = r.material as THREE.MeshBasicMaterial;
      r.visible = air > 0.01;
      const phase = ((now / 2600) + i / rings.length) % 1;
      // Start at the aerial so the wave is seen leaving the router. Stop inside SUBJECT: a
      // ring leaving the frame looks like a wave hitting a wall.
      const size = 0.12 + phase * 2.9;
      r.quaternion.copy(camera.quaternion);
      r.scale.set(size, size, size);
      // fade in as well as out, so no ring pops into being at the aerial (tubes do the same)
      paint.opacity = Math.min(1, phase * 6) * (1 - phase) * 0.5 * air;
    });

    renderer.render(scene, camera);
    if (!still && seen) raf = requestAnimationFrame(frame);
  }

  /**
   * Pause while scrolled off screen. Hidden tabs stop rAF on their own, scrolled canvases
   * don't, so on a phone the house kept drawing behind the plan list. The step is capped,
   * so it resumes where it left off.
   */
  let seen = true;
  const watcher = new IntersectionObserver((entries) => {
    const now = entries.some((entry) => entry.isIntersecting);
    if (now === seen) return;
    seen = now;
    if (seen) start();
    else cancelAnimationFrame(raf);
  });
  watcher.observe(canvas);

  function start(): void {
    cancelAnimationFrame(raf);
    if (still) frame();
    else if (seen) raf = requestAnimationFrame(frame);
  }
  start();
  // named so stop() can remove it: anonymous, every address left one behind, keeping its
  // renderer and scene alive
  const onResize = (): void => { if (still) frame(); };
  window.addEventListener('resize', onResize);

  return {
    setMode(next: Mode) {
      if (next === mode) return;
      previous = mode;
      mode = next;
      changedAt = performance.now();
      if (still) frame();
    },
    setColour(next: string) {
      colour = next;
      for (const r of Object.values(ROUTES)) r.setColour(next);
      for (const r of rings) (r.material as THREE.MeshBasicMaterial).color.set(next);
      if (still) frame();
    },
    setSpeed(next: number) { mbps = next; if (still) frame(); },
    setStill(next: boolean) { still = next; start(); },
    stop() {
      cancelAnimationFrame(raf);
      watcher.disconnect();
      window.removeEventListener('resize', onResize);
      for (const r of Object.values(ROUTES)) r.dispose();
      // geometries, materials and render targets aren't garbage collected, and leaking a
      // scene per address is the classic version of this bug
      scene.traverse((o) => {
        const mesh = o as Partial<THREE.Mesh>;
        mesh.geometry?.dispose();
        (mesh.material as THREE.Material | undefined)?.dispose();
      });
      pmrem.dispose();
      renderer.dispose();
    },
  };
}
