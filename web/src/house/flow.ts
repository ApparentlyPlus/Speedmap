/**
 * The signal, as light flowing along a path.
 *
 * Particles were the wrong primitive. A particle travelling 0 → 1 has to go back to 0, and
 * however it is faded that reset is a discontinuity you can see — which is what made the
 * motion look like it was stuttering rather than flowing.
 *
 * A tube has no such moment. The geometry is fixed and what moves is a pattern scrolling
 * through it, so every frame is the same picture shifted slightly: there is nothing to
 * restart. It also renders as one draw call however long the path is, and it occludes and is
 * occluded correctly because it is real geometry rather than billboards.
 */
import * as THREE from "three";

const VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = `
precision highp float;
varying vec2 vUv;
uniform vec3  uColour;
uniform float uTime;
uniform float uSpeed;    // how fast the bands travel
uniform float uDensity;  // how many are on the path at once
uniform float uBright;
uniform float uFadeIn;   // how much of the start to ease in over

void main() {
  // One sawtooth per band. fract() is continuous under scrolling, so there is no seam.
  float wave = fract(vUv.x * uDensity - uTime * uSpeed);

  // A head that rises quickly and a tail that falls away slowly: the asymmetry is what
  // reads as direction. Symmetrical bands look like a barber's pole and have no flow.
  float head = smoothstep(0.0, 0.06, wave);
  float tail = 1.0 - smoothstep(0.06, 0.62, wave);
  float band = head * tail;

  // Faded at both ends of the path, so light is never seen appearing or vanishing at a cut.
  float ends = smoothstep(0.0, uFadeIn, vUv.x) * (1.0 - smoothstep(0.86, 1.0, vUv.x));

  // Brightest along the centre line of the tube, so it reads as a filament in a glow
  // rather than as a painted pipe.
  float core = 1.0 - abs(vUv.y - 0.5) * 2.0;
  core = pow(max(core, 0.0), 1.6);

  float a = band * ends * (0.25 + core * 0.75);
  vec3 lit = mix(uColour, vec3(1.0), core * band * 0.55);
  gl_FragColor = vec4(lit * a * uBright, a);
}`;

export type Point = readonly [number, number, number];

export type Flow = {
  readonly mesh: THREE.Mesh;
  step: (dt: number) => void;
  setColour: (hex: string) => void;
  setTraffic: (of: { speed: number; density: number }) => void;
  setStrength: (v: number) => void;
  dispose: () => void;
};

export type FlowOptions = {
  readonly colour?: string;
  readonly radius?: number;
  readonly steps?: number;
  readonly fadeIn?: number;
  readonly speed?: number;
  readonly density?: number;
  readonly bright?: number;
};

export function flow(points: readonly Point[], options: FlowOptions = {}): Flow {
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
  const geometry = new THREE.TubeGeometry(curve, options.steps ?? 80, options.radius ?? 0.1, 10, false);
  const material = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
    uniforms: {
      uColour: { value: new THREE.Color(options.colour ?? '#38bdf8') },
      uTime: { value: 0 },
      uSpeed: { value: options.speed ?? 0.3 },
      uDensity: { value: options.density ?? 3 },
      uBright: { value: options.bright ?? 1.6 },
      // A path that starts at a visible emitter — a dish on a roof — should be bright where
      // it leaves it. One that arrives from off-screen can afford to ease in.
      uFadeIn: { value: options.fadeIn ?? 0.1 },
    },
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = 2;
  return {
    mesh,
    step(dt: number) { material.uniforms['uTime']!.value += dt; },
    setColour(hex: string) { (material.uniforms['uColour']!.value as THREE.Color).set(hex); },
    setTraffic({ speed, density }: { speed: number; density: number }) {
      material.uniforms['uSpeed']!.value = speed;
      material.uniforms['uDensity']!.value = density;
    },
    setStrength(v: number) { material.uniforms['uBright']!.value = v; },
    dispose() { geometry.dispose(); material.dispose(); },
  };
}

/** A ring that expands and fades: what a signal leaving an aerial looks like. */
export function ring(colour: string): THREE.Mesh {
  // Left in its own plane rather than laid flat: it is turned to face the camera each frame,
  // and a ring already rotated into the ground would then be turned twice.
  const geometry = new THREE.RingGeometry(0.92, 1.0, 72);
  const material = new THREE.MeshBasicMaterial({
    color: colour, transparent: true, opacity: 0.4,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    depthWrite: false,
    /*
     * Not depth tested at all.
     *
     * Sorting is per object, not per fragment, and a ring centred on the router passes
     * through the house — part of it in front, part behind. Whichever way that one object
     * sorts, the half on the wrong side is cut away, which drew each wave as an arc with a
     * clean bite taken out of it along the roofline.
     *
     * And the occlusion was wrong to want in the first place: this is radiating energy
     * rather than a solid, and the whole point of opening the walls is to watch it leave
     * the router. Light that stops at a wall it is supposed to be passing through is a
     * worse lie than light drawn in front of one.
     */
    depthTest: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  // After the house, so "in front" is what it resolves to where they overlap.
  mesh.renderOrder = 4;
  return mesh;
}
