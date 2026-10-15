// response types come from the OpenAPI schema

import type { components } from "./schema";

export type Result = components["schemas"]["Result"];
export type Options = components["schemas"]["Options"];
export type Buyable = components["schemas"]["Buyable"];
export type Operator = components["schemas"]["Operator"];
export type Probed = components["schemas"]["Probed"];
export type StreetDetail = components["schemas"]["StreetDetail"];
export type AddressDetail = components["schemas"]["AddressDetail"];
export type ReportIn = components["schemas"]["ReportIn"];
export type Report = components["schemas"]["Report"];

// same origin, proxied the same way in dev
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

export function search(
  query: string,
  signal?: AbortSignal,
  kind?: "street",
): Promise<Result[]> {
  const only = kind === undefined ? "" : `&kind=${kind}`;
  return get<Result[]>(`/search?q=${encodeURIComponent(query)}${only}`, signal);
}

export function options(addressId: number, signal?: AbortSignal): Promise<Options> {
  return get<Options>(`/addresses/${addressId}/options`, signal);
}

export function probe(
  addressId: number,
  provider: string,
  signal?: AbortSignal,
): Promise<Probed[]> {
  const where = `/addresses/${addressId}/probe?provider=${encodeURIComponent(provider)}`;
  return send<Probed[]>("POST", where, signal);
}

// make an unfiled door on a known street, the common case
export function askFor(
  streetId: number,
  streetNo: string,
  signal?: AbortSignal,
): Promise<Result> {
  return send<Result>("POST", `/streets/${streetId}/addresses`, signal, {
    street_no: streetNo,
  });
}



export function report(filed: ReportIn, signal?: AbortSignal): Promise<Report> {
  return send<Report>("POST", "/reports", signal, filed);
}

export function street(streetId: number, signal?: AbortSignal): Promise<StreetDetail> {
  return get<StreetDetail>(`/streets/${streetId}`, signal);
}

export function address(addressId: number, signal?: AbortSignal): Promise<AddressDetail> {
  return get<AddressDetail>(`/addresses/${addressId}`, signal);
}

