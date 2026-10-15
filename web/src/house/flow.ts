// the signal as light flowing along a path (particles didn't work)
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
  // a sawtooth per band, fract() has no seam under scrolling
  float wave = fract(vUv.x * uDensity - uTime * uSpeed);

  // fast rise, slow tail, which is what reads as direction. Symmetric bands look like a barber's pole
  float head = smoothstep(0.0, 0.06, wave);
  float tail = 1.0 - smoothstep(0.06, 0.62, wave);
  float band = head * tail;

  // faded at both ends so nothing pops in at a cut
  float ends = smoothstep(0.0, uFadeIn, vUv.x) * (1.0 - smoothstep(0.86, 1.0, vUv.x));

  // brightest on the centre line, a filament in a glow and not a painted pipe
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
      // bright at a visible emitter (the dish), eased in when it comes from off screen
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

// expanding, fading ring leaving an aerial
export function ring(colour: string): THREE.Mesh {
  // left upright, it gets turned to the camera every frame
  const geometry = new THREE.RingGeometry(0.92, 1.0, 72);
  const material = new THREE.MeshBasicMaterial({
    color: colour, transparent: true, opacity: 0.4,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    depthWrite: false,
    // no depth test, the ring passes through the house and per-object sorting gets it wrong
    depthTest: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = 4; // after the house, so overlaps resolve to "in front"
  return mesh;
}
