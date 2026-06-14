/**
 * The API, with its shapes taken from its own schema.
 *
 * Nothing here declares what a response looks like. The types come from `schema.ts`, which
 * is generated from the OpenAPI document the server publishes, so a field renamed on the
 * server fails the build here rather than arriving as undefined and rendering as nothing.
 */

import type { components } from "./schema";

export type Result = components["schemas"]["Result"];
export type Options = components["schemas"]["Options"];
export type Buyable = components["schemas"]["Buyable"];
export type Operator = components["schemas"]["Operator"];

/** Same origin in production behind Caddy, and proxied to the same place in development. */
const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const answer = await fetch(`${BASE}${path}`, {
    signal: signal ?? null,
    headers: { Accept: "application/json" },
  });
  if (!answer.ok) {
    throw new ApiError(answer.status, `${path} answered ${answer.status}`);
  }
  return (await answer.json()) as T;
}

export function search(query: string, signal?: AbortSignal): Promise<Result[]> {
  return get<Result[]>(`/search?q=${encodeURIComponent(query)}`, signal);
}

export function options(addressId: number, signal?: AbortSignal): Promise<Options> {
  return get<Options>(`/addresses/${addressId}/options`, signal);
}
