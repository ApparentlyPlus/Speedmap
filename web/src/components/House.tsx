/**
 * The address, drawn.
 *
 * One canvas and one scene, kept across renders: rebuilding it on every state change would
 * throw away a WebGL context and an environment map several times a second. What React
 * changes is three numbers on the scene — the mode, the colour and the speed — and the
 * scene animates its own way from wherever it was to wherever it has been told to be.
 */

import { useEffect, useRef } from "react";

import { house3d, type Mode, type Scene } from "../house/house3d";

export function House({
  mode,
  colour,
  mbps,
}: {
  readonly mode: Mode;
  readonly colour: string;
  readonly mbps: number;
}): React.ReactElement {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<Scene | null>(null);

  useEffect(() => {
    if (canvas.current === null) return;
    // Someone who asked for less motion gets the same scene, held still — which is why it
    // is composed to be worth looking at as one frame.
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const built = house3d(canvas.current, { mode, colour, mbps, still: calm.matches });
    scene.current = built;

    const follow = (): void => built.setStill(calm.matches);
    calm.addEventListener("change", follow);
    return () => {
      calm.removeEventListener("change", follow);
      built.stop();
      scene.current = null;
    };
    // Built once. Everything that changes after is pushed in below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => scene.current?.setMode(mode), [mode]);
  useEffect(() => scene.current?.setColour(colour), [colour]);
  useEffect(() => scene.current?.setSpeed(mbps), [mbps]);

  return <canvas className="house" ref={canvas} aria-hidden="true" />;
}
