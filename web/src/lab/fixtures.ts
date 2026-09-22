/**
 * Stand-in answers for the lab, so the new result screen can be built and argued about
 * without the API, the database or a network. Every scenario here is a real shape the
 * ranker produces, trimmed to the few plans a screen actually shows.
 */

import type { Geometry } from "geojson";

import type { Buyable, Options } from "../api/client";

export const ERMOU_BBOX = [23.71497, 37.97569, 23.734, 37.97785] as [number, number, number, number];
export const ERMOU_SHAPE = {"type": "MultiLineString", "coordinates": [[[23.714969, 37.977787], [23.715114, 37.977596], [23.715167, 37.977572], [23.715547, 37.977603]], [[23.715535, 37.977688], [23.715238, 37.977667], [23.71508, 37.977838]], [[23.7208, 37.977421], [23.717705, 37.977844], [23.716756, 37.977803], [23.715535, 37.977688]], [[23.715547, 37.977603], [23.715535, 37.977688]], [[23.715547, 37.977603], [23.716277, 37.977672]], [[23.72125, 37.977369], [23.722847, 37.977129], [23.728447, 37.976397]], [[23.728801, 37.976357], [23.734002, 37.975692]]]};

export const SHAPE = ERMOU_SHAPE as unknown as Geometry;

/**
 * The row this street is in the tiles, so the map keeps it in colour while the rest of the
 * city goes quiet. A fixture rather than a lookup: the lab answers without the API, and
 * this id is stable because the street is a component of a named road in a municipality.
 */
export const STREET_ID = 34815;

/** Where the camera lands. The middle of the box the street occupies. */
export const WHERE = {
  lon: (ERMOU_BBOX[0] + ERMOU_BBOX[2]) / 2,
  lat: (ERMOU_BBOX[1] + ERMOU_BBOX[3]) / 2,
};

function plan(
  provider: string,
  name: string,
  technology: string,
  family: string,
  speed: number,
  monthly: number,
  extra: Partial<Buyable> = {},
): Buyable {
  return {
    provider,
    provider_name: name.split(" ")[0] ?? provider,
    plan: name,
    technology,
    family,
    expected_mbps: String(speed),
    data_cap_gb: null,
    cost: {
      total: String(monthly.toFixed(2)),
      recurring: String(monthly.toFixed(2)),
      upfront: "0.00",
      complete: true,
    },
    basis: "advertised",
    tests: 0,
    confidence: 0,
    enough: speed >= 100,
    why: "",
    ...extra,
  } as Buyable;
}

function answer(options: Buyable[]): Options {
  return {
    address_id: 1,
    need_mbps: "100",
    known: {},
    operators: [],
    options,
  } as unknown as Options;
}

export type Scenario = {
  readonly key: string;
  /** What the reader typed, and where it is. */
  readonly name: string;
  readonly place: string;
  readonly answer: Options;
};

/**
 * The five shapes worth designing against. They are not evenly likely: fiber and vectored
 * copper are most addresses, and satellite is a few thousand. The screen has to hold all
 * of them without one reading as an error.
 */
export const SCENARIOS: readonly Scenario[] = [
  {
    key: "fiber",
    name: "Ερμού 12",
    place: "ΑΘΗΝΑ, ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ",
    answer: answer([
      plan("TELEKOM", "Telekom Fiber 1Gbps Unlimited", "FTTH", "fiber", 1000, 35.9),
      plan("VODAFONE", "Vodafone Full Fiber 500 plus", "FTTH", "fiber", 500, 28.71),
      plan("NOVA", "Nova Fiber 300", "FTTH", "fiber", 300, 26.0),
      plan("TELEKOM", "Telekom Fiber 300 Unlimited", "FTTH", "fiber", 300, 27.9),
      plan("VODAFONE", "Vodafone Fiber 100", "VECT_VDSL", "copper", 100, 26.25),
    ]),
  },
  {
    key: "vectored",
    name: "Αχαρνών 55",
    place: "ΑΘΗΝΑ, ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ",
    answer: answer([
      plan("NOVA", "Nova Fiber 100", "VECT_VDSL", "copper", 100, 21.0),
      plan("VODAFONE", "Vodafone Fiber 100", "VECT_VDSL", "copper", 100, 26.25),
      plan("TELEKOM", "Telekom Fiber 100", "VECT_VDSL", "copper", 100, 27.9),
      plan("TELEKOM", "Telekom 5G WiFi Double Play 300", "FWA_5G", "wireless", 120, 35.9),
    ]),
  },
  {
    key: "legacy",
    name: "Θερίσου 8",
    place: "ΧΑΝΙΑ, ΔΗΜΟΣ ΧΑΝΙΩΝ",
    answer: answer([
      plan("TELEKOM", "Telekom Gigamax Unlimited", "MOBILE", "wireless", 120, 41.0),
      plan("NOVA", "Nova Unlimited All", "MOBILE", "wireless", 100, 30.0),
      plan("VODAFONE", "Vodafone VDSL 50", "VDSL", "copper", 50, 24.04),
      plan("TELEKOM", "Telekom ADSL 24", "ADSL", "copper", 24, 24.29),
    ]),
  },
  {
    key: "wireless",
    name: "Λεωφόρος Μαραθώνος 104",
    place: "ΠΙΚΕΡΜΙ, ΔΗΜΟΣ ΡΑΦΗΝΑΣ - ΠΙΚΕΡΜΙΟΥ",
    answer: answer([
      plan("TELEKOM", "Telekom 5G WiFi Double Play 300", "FWA_5G", "wireless", 120, 35.9),
      plan("VODAFONE", "Vodafone RED 80GB", "MOBILE", "wireless", 120, 23.8),
      plan("NOVA", "Nova Unlimited+ 40GB", "MOBILE", "wireless", 100, 25.0),
    ]),
  },
  {
    key: "satellite",
    name: "Αγίου Νικολάου 2",
    place: "ΑΝΑΦΗ, ΔΗΜΟΣ ΑΝΑΦΗΣ",
    answer: answer([
      plan("STARLINK", "Starlink Residential 200 Mbps", "SAT", "satellite", 140, 45.0),
      plan("STARLINK", "Starlink Residential 100 Mbps", "SAT", "satellite", 70, 35.0),
    ]),
  },
  {
    key: "none",
    name: "Ανώνυμος οδός",
    place: "ΔΗΜΟΣ ΠΥΛΟΥ - ΝΕΣΤΟΡΟΣ",
    answer: answer([]),
  },
];
