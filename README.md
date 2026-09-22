# Speedmap

Speedmap shows what broadband is available at an address in Greece. It joins EETT's national coverage register to an address index built from the same register and street geometry from OpenStreetMap, then draws every street in the country coloured by the best line that reaches it. Where an operator publishes a tariff, the result also carries a price; where someone has run a speed test nearby, it carries a measurement.

The database holds 1,796,105 addresses, 91,672 streets across 333 municipalities, and 14.6M coverage rows, at roughly 18 GB.

## Data Sources

| Source | Provides | Volume |
|---|---|---|
| EETT register (`broadband-assist.gov.gr`) | Filed services: who reaches where, on which technology, at which speed class | 1,362,340 services, 24 operators |
| OpenStreetMap | Street geometry, grouped into connected runs of a named road per municipality | 91,672 streets |
| Ookla open data | Measured download and upload speeds, per 600 m tile | 133,026 cells |
| Operator availability checkers | Live serviceability for Telekom, Vodafone and Nova | on demand |
| Published tariffs | Monthly price, setup fee, contract length, data cap | 74 plans, 25 providers |

The register is an unauthenticated PostgREST API. Its page cap is 500 and it truncates silently rather than erroring, so the loader steps by 500 and records its resume key per dataset.

## How The Speed Figure Is Derived

The register files speed *classes*, not speeds: the finest value available is a band such as "100-300 Mbps". It also leaves the band empty on most filings, including 70.8% of the 1,071,133 fiber rows.

The figure shown is therefore anchored on the technology rather than read from the band:

```
best_mbps = least(technology.sold_mbps, the filed band's ceiling)
```

`sold_mbps` is what operators actually retail on each kind of line, taken from the scraped tariffs:

| Technology | sold_mbps | Basis |
|---|---|---|
| ADSL | 24 | The single ADSL plan on file |
| VDSL | 50 | Every VDSL plan on file is 50 |
| Vectored VDSL | 100 | Telekom, Vodafone and Nova all retail 100 |
| DOCSIS | 300 | No coax is filed in Greece; set so a future filing reports something |
| FTTH | 1000 | Plans run 100 to 3000 |

The cap uses `a4a_nordown`, the register's normally available speed, rather than `a4a_maxdown`. It is filed in exactly the rows `maxdown` is and is never higher, so it can only lower a figure. Using it roughly doubles the number of streets identifiable as being on 10 Mbps or less.

A filing can pull a figure down but never lift it. Resulting distribution across the 84,355 streets that have a figure:

| Mbps | Streets | Share |
|---|---|---|
| 1000 | 38,886 | 46.1% |
| 100 | 30,290 | 35.9% |
| 50 | 6,252 | 7.4% |
| 30 | 3,907 | 4.6% |
| 24 | 692 | 0.8% |
| 10 or less | 4,328 | 5.1% |

## Pipeline

Raw register tables land in `raw_*` and are never modified. Everything else is derived by re-runnable steps in `normalise/steps/`, executed in filename order by `make build`:

| Step | Produces |
|---|---|
| `010_municipality` | The 333 Kallikratis municipalities, reprojected to 4326 |
| `030_coverage` | Point-located services (fiber, coax) |
| `040_coverage_area` | Copper cabinet polygons, reprojected from Greek Grid |
| `050_address_coverage` | What reaches each address, by point match or cabinet containment |
| `065_address_street` | Pins each address to the nearest road of its name |
| `070_wireless` | Fixed wireless, matched to the 100 m register grid by arithmetic |
| `090_wholesale` | Refreshes the seller-to-infrastructure view |
| `100_builder_coverage` | Anyone who passes premises but files no retail service there |
| `110_street_reach` | Which operators reach each street, and at what speed |
| `120_street_speed` | The street's own figure, taken from `110` |
| `130_municipality_coverage` | Per-municipality fiber share and measured averages |

Each step deletes its own previous output before rebuilding, so a withdrawn filing disappears rather than persisting. `address_coverage` is written by three steps, so rows carry a `built_by` column identifying which one owns them.

The register keeps two books and both are read. A service filing says an operator sells a line at a point; an infrastructure filing says one has built past a door. Reading only the first understates anyone who builds and files little: Telekom passes 1.09 million doors and files 36,012 services, so the map credited it with 23,041 fiber addresses against Vodafone's 601,473, which described who fills in which form rather than what is in the ground. `100_builder_coverage` credits premises passed to whoever passed them, incumbent and altnet alike.

Operators carry a `role`. A `retail` operator is one a household can buy from. The `infrastructure` ones cannot be bought from directly: wholesale builders who pass premises for others to sell over, plus Metadosis, which files services and publishes no tariff. Both colour the map, since fiber in the ground decides whether anyone will ever sell a gigabit down the street, but they are listed apart so the panel stops offering suppliers nobody can choose.

The register also files one company under four names. OTE, OTE UltraFast and two rural concessions are all Telekom to anyone buying a line. The alias rows stay in `provider`, because `register_id` is how `raw_*` is joined, and every step resolves through `credited_to` before storing an id.

A street's reach comes from two routes unioned: filings against addresses pinned to the street, and cabinet polygons the street intersects. Builders file addresses and no polygons, and roughly half of all streets have no filed address, so either route alone loses a different half. Cabinet polygons are capped at 5,000,000 m² by `cabinet_m2()`; larger filings are exchange regions and say nothing about an individual street.

Mobile and fixed wireless are excluded from street and municipality figures. 5G reaches nearly every address and files a 300-1000 band where it does, which flattens the map to a single value.

Schema changes are ordered, checksummed migrations in `normalise/migrations/` (61 of them), applied by `make migrate`.

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

MapLibre GL reading PMTiles archives by range request. Three vector layers, cut by tippecanoe at zoom 4 to 14 into two archives:

`speedmap.pmtiles`

- `streets`: one feature per street, carrying the overall figure plus a per-operator field, so the map can be filtered to a single operator without repainting a colour that operator cannot sell. A field carries `role: infrastructure` in `schema/tiles.yaml` when its operator retails nothing, and the panel reads that rather than listing them again.
- `regions`: one feature per municipality, for zooms below 11 where a street is a fraction of a pixel.

`cells.pmtiles`

- `cells`: Ookla tiles as the square that was measured, clipped to the country. About 4% of Greece has any measurement, so an empty view is normal.

The squares sit apart because the map draws them or the streets, never both. Sharing an archive meant every zoom out fetched and decompressed squares the coverage view does not draw, half of every tile at the country zooms. Now MapLibre asks for that archive only once the reader switches to Measured.

Features are written in a fixed order. Tippecanoe writes them in the order it reads them and the renderer draws them in that order, so without an `order by` a rebuild can swap which of two crossing streets is on top, which is a visible change from no change at all.

Field names are defined once in `schema/tiles.yaml` and generated into both the Python builder and the TypeScript renderer, so a renamed field breaks the build rather than silently rendering as `undefined`.

MapLibre parses tiles on one worker unless it is told otherwise. `web/src/map/engine.ts` sets the pool to eight and registers one PMTiles protocol for the page.

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

`make check` runs ruff, mypy in strict mode, a lint that bans numeric fallbacks, the two generated contracts, 721 Python tests and 46 frontend tests. Eight of the frontend tests drive a real browser through Playwright and skip unless a dev server is answering on `127.0.0.1:5173`.

`make audit` is separate and runs the eight SQL invariants in `tests/invariants/` against the loaded database. The test suite runs the same files against an empty scratch database, which proves only that each one fires when a violation is planted beneath it. Running them against real data is a different check and has caught different problems.

## Known Limitations

- Addresses match streets about 63% of the time. `065_address_street` pins each one to the nearest road of its name in its municipality; where no road of that name exists, there is no geometry to show and the pin stays null.
- A street is one connected run of road. Ways within about 55 m of each other are one street, which steps over a square or a dual carriageway without merging two roads a block apart. Where a name covers several runs, each is its own row: before this, one row held all of them, a cabinet reaching one coloured the lot, and 516 of those rows spanned more than 20 km.
- The register files ADSL above its physical ceiling on 512 rows, including five at a gigabit. Those are held to 24 Mbps, so the map disagrees with the filing in those places.
- The Cosmote address scrape covers 43% of streets, which limits which addresses the Telekom and Nova checkers can be asked about. Nova's adapter works around this by searching the operator's live street list; Telekom's cannot. The scrape and its adapter keep the name of the site they read, which is `cosmote.gr`; the operator they write to the database is `TELEKOM`.
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
