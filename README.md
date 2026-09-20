# Speedmap

Speedmap shows what broadband is available at an address in Greece. It joins EETT's national coverage register to an address index built from the same register and street geometry from OpenStreetMap, then draws every street in the country coloured by the best line that reaches it. Where an operator publishes a tariff, the result also carries a price; where someone has run a speed test nearby, it carries a measurement.

The database holds 1,796,105 addresses, 80,756 streets across 333 municipalities, and 12.8M coverage rows, at roughly 17 GB.

## Data Sources

| Source | Provides | Volume |
|---|---|---|
| EETT register (`broadband-assist.gov.gr`) | Filed services: who reaches where, on which technology, at which speed class | 1,362,340 services, 24 operators |
| OpenStreetMap | Street geometry, grouped into named streets per municipality | 80,756 streets |
| Ookla open data | Measured download and upload speeds, per 600 m tile | 133,026 cells |
| Operator availability checkers | Live serviceability for OTE, Vodafone and Nova | on demand |
| Published tariffs | Monthly price, setup fee, contract length, data cap | 74 plans, 25 providers |

The register is an unauthenticated PostgREST API. Its page cap is 500 and it truncates silently rather than erroring, so the loader steps by 500 and records its resume key per dataset.

## How The Speed Figure Is Derived

The register files speed *classes*, not speeds: the finest value available is a band such as "100-300 Mbps". It also leaves the band empty on most filings, including 70.8% of the 1,071,133 fibre rows.

The figure shown is therefore anchored on the technology rather than read from the band:

```
best_mbps = least(technology.sold_mbps, the filed band's ceiling)
```

`sold_mbps` is what operators actually retail on each kind of line, taken from the scraped tariffs:

| Technology | sold_mbps | Basis |
|---|---|---|
| ADSL | 24 | The single ADSL plan on file |
| VDSL | 50 | Every VDSL plan on file is 50 |
| Vectored VDSL | 100 | OTE, Vodafone and Nova all retail 100 |
| DOCSIS | 300 | No coax is filed in Greece; set so a future filing reports something |
| FTTH | 1000 | Plans run 100 to 3000 |

The cap uses `a4a_nordown`, the register's normally available speed, rather than `a4a_maxdown`. It is filed in exactly the rows `maxdown` is and is never higher, so it can only lower a figure. Using it roughly doubles the number of streets identifiable as being on 10 Mbps or less.

A filing can pull a figure down but never lift it. Resulting distribution across the 75,353 streets that have a figure:

| Mbps | Streets | Share |
|---|---|---|
| 1000 | 24,778 | 32.9% |
| 100 | 36,249 | 48.1% |
| 50 | 6,860 | 9.1% |
| 30 | 3,361 | 4.5% |
| 24 | 608 | 0.8% |
| 10 or less | 3,497 | 4.6% |

## Pipeline

Raw register tables land in `raw_*` and are never modified. Everything else is derived by re-runnable steps in `normalise/steps/`, executed in filename order by `make build`:

| Step | Produces |
|---|---|
| `010_municipality` | The 333 Kallikratis municipalities, reprojected to 4326 |
| `030_coverage` | Point-located services (fibre, coax) |
| `040_coverage_area` | Copper cabinet polygons, reprojected from Greek Grid |
| `050_address_coverage` | What reaches each address, by point match or cabinet containment |
| `070_wireless` | Fixed wireless, matched to the 100 m register grid by arithmetic |
| `090_wholesale` | Refreshes the seller-to-infrastructure view |
| `100_builder_coverage` | Altnets that pass premises but file no retail service |
| `110_street_reach` | Which operators reach each street, and at what speed |
| `120_street_speed` | The street's own figure, taken from `110` |
| `130_municipality_coverage` | Per-municipality fibre share and measured averages |

Each step deletes its own previous output before rebuilding, so a withdrawn filing disappears rather than persisting. `address_coverage` is written by three steps, so rows carry a `built_by` column identifying which one owns them.

A street's reach comes from two routes unioned: filings against addresses on the street, and cabinet polygons the street intersects. Builders file addresses and no polygons, and roughly half of all streets have no filed address, so either route alone loses a different half. Cabinet polygons are capped at 5,000,000 m² by `cabinet_m2()`; larger filings are exchange regions and say nothing about an individual street.

Mobile and fixed wireless are excluded from street and municipality figures. 5G reaches nearly every address and files a 300-1000 band where it does, which flattens the map to a single value.

Schema changes are ordered, checksummed migrations in `normalise/migrations/` (57 of them), applied by `make migrate`.

## API

FastAPI, read-only except for three endpoints. Runs on `:8000`.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | Row counts, to confirm the database is built |
| `GET` | `/search` | Addresses and streets, Greek or Greeklish |
| `GET` | `/addresses/{id}` | One address, with every filed offer |
| `GET` | `/addresses/{id}/options` | What is buyable there, ranked, with costs |
| `POST` | `/addresses/{id}/probe` | Asks one operator live |
| `GET` | `/streets/{id}` | One street, its geometry and the offers along it |
| `POST` | `/streets/{id}/addresses` | Creates an address the register never filed |
| `POST` | `/reports` | Records that something looks wrong |
| `GET` | `/health/adapters` | Per-operator checker state |

Search runs three widening tiers: literal prefix, word-start, then trigram similarity. The fuzzy tier matches against a materialised view of the 126,151 distinct address spellings rather than all 1.8M rows, which keeps it near 45 ms instead of 750 ms.

`schema/openapi.json` is generated from the application and checked by `make lint`. The frontend's types are generated from it in turn.

## Map

MapLibre GL reading PMTiles archives by range request. Three vector layers, cut by tippecanoe at zoom 4 to 14:

- `streets`: one feature per street, carrying the overall figure plus a per-operator field, so the map can be filtered to a single operator without repainting a colour that operator cannot sell.
- `cells`: Ookla tiles as the square that was measured, clipped to the country. About 4% of Greece has any measurement, so an empty view is normal.
- `regions`: one feature per municipality, for zooms below 11 where a street is a fraction of a pixel.

Field names are defined once in `schema/tiles.yaml` and generated into both the Python builder and the TypeScript renderer, so a renamed field breaks the build rather than silently rendering as `undefined`.

The basemap and building footprints are separate archives built with planetiler from an OSM extract and Overture footprints. They are not produced by this repository.

## Local Development

Requires Postgres 18 with PostGIS, Python 3.13, and Node. `tippecanoe` is needed only to cut tiles.

```bash
make setup        # .venv and dependencies
make bootstrap    # migrate, load the register, build derived tables
make api          # http://localhost:8000
```

```bash
cd web
npm install
npm run dev       # http://localhost:5173, proxies /api to :8000
```

The dev server proxies the API so both run same-origin, matching production behind Caddy.

## Make Targets

| Target | Purpose |
|---|---|
| `setup` | Create `.venv` and install dependencies |
| `bootstrap` | Bare clone to loaded database |
| `migrate` / `migrate-status` | Apply or list pending migrations |
| `build` | Rebuild derived tables from `raw_*` |
| `audit` | Run data invariants against the built database |
| `tiles` | Cut the map tiles |
| `codegen` | Regenerate the tile contract and OpenAPI document |
| `api` | Run the API |
| `check` | Lint, typecheck, and both test suites |
| `db-check` / `progress` | Database reachability and register load progress |

## Testing

`make check` runs ruff, mypy in strict mode, a lint that bans numeric fallbacks, the two generated contracts, 713 Python tests and 46 frontend tests. Eight of the frontend tests drive a real browser through Playwright and skip unless a dev server is answering on `127.0.0.1:5173`.

`make audit` is separate and runs the six SQL invariants in `tests/invariants/` against the loaded database. The test suite runs the same files against an empty scratch database, which proves only that each one fires when a violation is planted beneath it. Running them against real data is a different check and has caught different problems.

## Known Limitations

- Addresses match streets about 63% of the time. The join is on municipality and folded street name; where it misses, there is no street geometry to show.
- A street is every road of that name within a municipality. Usually one road, sometimes several disconnected stretches kilometres apart.
- The register files ADSL above its physical ceiling on 512 rows, including five at a gigabit. Those are held to 24 Mbps, so the map disagrees with the filing in those places.
- The Cosmote address scrape covers 43% of streets, which limits which addresses the OTE and Nova checkers can be asked about. Nova's adapter works around this by searching the operator's live street list; Cosmote's cannot.
- A street figure describes the best line reaching the street, not line quality at a specific door. Distance from the cabinet is not modelled. The measured view is the counterweight.
- Prices are absent for operators that publish none, and three HCN plans have no setup fee published, so their totals are floors rather than exact.

## Attribution and Licensing

The code in this repository is MIT licensed. See `LICENSE`. That covers the code only. Every dataset it loads carries its own terms, and those terms travel with the data rather than with the code, so a clone of this repository is not a licence to republish what a build of it produces.

**OpenStreetMap.** Street geometry and the basemap archive come from an OSM extract, licensed under the [ODbL](https://opendatacommons.org/licenses/odbl/). Credited in the map as:

> © OpenStreetMap contributors

**Overture Maps.** Building footprints come from the Overture buildings theme, also ODbL, which conflates OSM with several other sources that ask to be named individually:

> © OpenStreetMap contributors, Overture Maps Foundation, Microsoft, Esri Community Maps contributors, Google Open Buildings

**Ookla.** The measured speeds come from Ookla's open dataset under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Ookla specify the wording, so it is reproduced verbatim, and the quarter and the access date in it are the ones this build actually used:

> Speedtest® by Ookla® Global Fixed and Mobile Network Performance Maps. Based on analysis by Ookla of Speedtest Intelligence® data for Q2 2026. Provided by Ookla and accessed 10 September 2026. Ookla trademarks used under license and reprinted with permission.

The NC term is the binding one here. Anything built from these tiles is non-commercial, and SA means a derived dataset carries the same licence forward.

**EETT register.** The coverage filings come from the national register at `broadband-assist.gov.gr`, published by the General Secretariat of Telecommunications and Postal Services. It is a public endpoint but it is not open data. Its [terms](https://www.broadband-assist.gov.gr/public/terms.html) reserve the content to the Secretariat, allow one local copy for personal and non-commercial use with attribution kept, and prohibit commercial exploitation and modification. Treat this repository as a personal and non-commercial tool, and ask the Secretariat before doing anything else with the register.

**Tariffs and checkers.** Plan prices and live serviceability answers are each operator's own material, read from their public pages. They are cached to run the site and attributed to the operator wherever they appear.

**Libraries.** The map runs on [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) (BSD 3-Clause). Label glyphs are served from `fonts.openmaptiles.org`, where each family keeps its own upstream licence, mostly SIL Open Font License. Tiles are cut with [tippecanoe](https://github.com/felt/tippecanoe) (BSD 2-Clause) and the basemap with [planetiler](https://github.com/onthegomap/planetiler) (Apache 2.0).

All of the above is shown in the site at `/attribution`, one click from a corner of every map. The page is generated from `web/src/credits.ts`, which is the only list of sources the frontend keeps, so a source added there is credited and a source added anywhere else is not credited at all.
