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
export type Probed = components["schemas"]["Probed"];

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

async function send<T>(
  method: string,
  path: string,
  signal?: AbortSignal,
  body?: unknown,
): Promise<T> {
  const answer = await fetch(`${BASE}${path}`, {
    method,
    signal: signal ?? null,
    headers:
      body === undefined
        ? { Accept: "application/json" }
        : { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? null : JSON.stringify(body),
  });
  if (!answer.ok) {
    throw new ApiError(answer.status, `${path} answered ${answer.status}`);
  }
  return (await answer.json()) as T;
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

/**
 * Ask one operator. One at a time on purpose: a checker takes between two and eight
 * seconds, and asking all three behind a single request makes the reader wait for the
 * slowest before learning anything about the other two.
 */
export function probe(
  addressId: number,
  provider: string,
  signal?: AbortSignal,
): Promise<Probed[]> {
  const where = `/addresses/${addressId}/probe?provider=${encodeURIComponent(provider)}`;
  return send<Probed[]>("POST", where, signal);
}

/**
 * Ask for a number the register never filed, on a street it did.
 *
 * The street is known and the door is not, which is the common case rather than the odd
 * one. Made once and kept: from here it is an address like any other, and the answers the
 * operators give about it belong to it rather than to this visit.
 */
export function askFor(
  streetId: number,
  streetNo: string,
  signal?: AbortSignal,
): Promise<Result> {
  return send<Result>("POST", `/streets/${streetId}/addresses`, signal, {
    street_no: streetNo,
  });
}
