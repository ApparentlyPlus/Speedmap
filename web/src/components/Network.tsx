/**
 * The network behind the page.
 *
 * Nodes drifting slowly, joined to whichever neighbours are close enough, drawn faintly in
 * the two colours the speed ramp runs between. It is the map this site is about, reduced
 * until it is texture rather than information — anything more legible would invite reading,
 * and there is nothing here to read.
 *
 * Canvas rather than SVG. A few hundred animated nodes in the DOM stutter on a phone, and
 * this has to cost nothing: it is the least important thing on the page.
 */

import { useEffect, useRef } from "react";

import { ACCENT, FAR } from "../tokens";

/** Enough to read as a network, few enough that the links stay countable by eye. */
const NODES_PER_MEGAPIXEL = 34;
const MAX_NODES = 90;

/** Beyond this, two nodes are not neighbours. Squared, to keep the loop free of roots. */
const REACH = 190;

/** Slow enough that nothing appears to be happening until you look for a while. */
const DRIFT = 0.045;

type Node = { x: number; y: number; dx: number; dy: number; warm: boolean };

function seed(width: number, height: number): Node[] {
  const area = (width * height) / 1_000_000;
  const count = Math.min(MAX_NODES, Math.max(18, Math.round(area * NODES_PER_MEGAPIXEL)));
  return Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    dx: (Math.random() - 0.5) * DRIFT,
    dy: (Math.random() - 0.5) * DRIFT,
    // A third of them at the far end of the ramp, so the field is mostly violet with cyan
    // through it rather than an even mix of two colours.
    warm: Math.random() > 0.34,
  }));
}

function draw(context: CanvasRenderingContext2D, nodes: Node[], w: number, h: number): void {
  context.clearRect(0, 0, w, h);

  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i];
    if (a === undefined) continue;
    for (let j = i + 1; j < nodes.length; j += 1) {
      const b = nodes[j];
      if (b === undefined) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const away = Math.hypot(dx, dy);
      if (away > REACH) continue;
      // Fading with distance is what makes it read as a mesh settling rather than a web.
      context.globalAlpha = (1 - away / REACH) * 0.16;
      context.strokeStyle = a.warm ? ACCENT : FAR;
      context.beginPath();
      context.moveTo(a.x, a.y);
      context.lineTo(b.x, b.y);
      context.stroke();
    }
  }

  for (const node of nodes) {
    context.globalAlpha = 0.5;
    context.fillStyle = node.warm ? ACCENT : FAR;
    context.beginPath();
    context.arc(node.x, node.y, 1.3, 0, Math.PI * 2);
    context.fill();
  }
  context.globalAlpha = 1;
}

export function Network(): React.ReactElement {
  const surface = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = surface.current;
    if (canvas === null) return;
    const context = canvas.getContext("2d");
    if (context === null) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let nodes: Node[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;

    const fit = (): void => {
      const ratio = Math.min(window.devicePixelRatio, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.lineWidth = 1;
      nodes = seed(width, height);
      draw(context, nodes, width, height);
    };

    const step = (): void => {
      for (const node of nodes) {
        node.x += node.dx;
        node.y += node.dy;
        // Wrapping rather than bouncing: a bounce puts a visible edge on something that is
        // supposed to have none.
        if (node.x < 0) node.x += width;
        if (node.x > width) node.x -= width;
        if (node.y < 0) node.y += height;
        if (node.y > height) node.y -= height;
      }
      draw(context, nodes, width, height);
      frame = window.requestAnimationFrame(step);
    };

    const wake = (): void => {
      window.cancelAnimationFrame(frame);
      // Nothing animates in a tab nobody is looking at.
      if (!still && !document.hidden) frame = window.requestAnimationFrame(step);
    };

    fit();
    wake();
    window.addEventListener("resize", fit);
    document.addEventListener("visibilitychange", wake);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", fit);
      document.removeEventListener("visibilitychange", wake);
    };
  }, []);

  return <canvas className="network" ref={surface} aria-hidden="true" />;
}
