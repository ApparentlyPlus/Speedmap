/**
 * The address, drawn. One canvas and one scene for the component's life: rebuilding on every
 * state change would throw away a WebGL context and an environment map several times a second.
 */

import { useEffect, useRef } from "react";

import { house3d, type Mode, type Scene } from "../house/house3d";

export function House({
  mode,
  colour,
  mbps,
  grounded = true,
}: {
  readonly mode: Mode;
  readonly colour: string;
  readonly mbps: number;
  /** False drops the plate, so the house stands on the page. */
  readonly grounded?: boolean;
}): React.ReactElement {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<Scene | null>(null);

  useEffect(() => {
    if (canvas.current === null) return;
    // reduced motion gets the same scene held still, which is why it's composed to work as
    // a single frame
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const built = house3d(canvas.current, {
      mode, colour, mbps, grounded, still: calm.matches,
    });
    scene.current = built;

    const follow = (): void => built.setStill(calm.matches);
    calm.addEventListener("change", follow);
    return () => {
      calm.removeEventListener("change", follow);
      built.stop();
      scene.current = null;
    };
    // built once, later changes are pushed in below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => scene.current?.setMode(mode), [mode]);
  useEffect(() => scene.current?.setColour(colour), [colour]);
  useEffect(() => scene.current?.setSpeed(mbps), [mbps]);

  return <canvas className="house" ref={canvas} aria-hidden="true" />;
}
