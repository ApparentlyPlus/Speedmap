<h1 align="center">Speedmap: What Broadband Actually Reaches Your Door in Greece</h1>

<p align="center">
  <a href="https://github.com/ApparentlyPlus/Speedmap/actions/workflows/python.yml"><img src="https://github.com/ApparentlyPlus/Speedmap/actions/workflows/python.yml/badge.svg" alt="Speedmap Python"></a>
  <a href="https://github.com/ApparentlyPlus/Speedmap/actions/workflows/web.yml"><img src="https://github.com/ApparentlyPlus/Speedmap/actions/workflows/web.yml/badge.svg" alt="Speedmap Web"></a>
  <a href="#license-and-attribution"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.14-3776ab" alt="Python 3.14">
  <img src="https://img.shields.io/badge/postgres-18%20%2B%20PostGIS-336791" alt="Postgres 18 + PostGIS">
</p>

Speedmap shows which broadband lines reach an address in Greece, how fast they really are, and what they cost. It takes EETT's national coverage register, builds an address index and a street layer out of it with OpenStreetMap, and draws every street in the country in the colour of the best line that reaches it. Type an address and you get the operators that can serve it, ranked, priced, and checked live against their own availability checkers.

The register is the only complete source of who reaches where, but it was never meant to be read by a person. It files speed *classes* instead of speeds, leaves the class empty on most fiber, lists one company under four names, and files a third of some networks with a postcode and no street. Most of this repository is about turning that into a map that is honest about what it knows.

> [!NOTE]
> This is a personal, non-commercial project. The code is MIT, but the data it loads is not mine to relicense, and some of it is explicitly non-commercial. Read [License and Attribution](#license-and-attribution) before doing anything with a build of it.

## Table of Contents

- [How It Works](#how-it-works)
- [Getting Started](#getting-started)
- [API](#api)
- [The Map](#the-map)
- [Testing](#testing)
- [Development](#development)
- [Known Limitations](#known-limitations)
- [License and Attribution](#license-and-attribution)

## How It Works

### Data Sources

| Source | Provides |
|---|---|
| EETT register (`broadband-assist.gov.gr`) | Who files a service or has built past a door, on which technology, at which speed class |
| OpenStreetMap | Street geometry, grouped into connected runs of a named road per municipality |
| Ookla open data | Measured speeds per ~600 m tile |
| Operator availability checkers | Live answers from Telekom, Vodafone and Nova |
| Published tariffs | Monthly price, setup fee, contract length, data cap |

### The Speed Figure

The register leaves the speed band empty on 70.8% of fiber filings, so the figure is anchored on the technology and the band can only cap it:

```
best_mbps = least(technology.sold_mbps, ceiling of the filed band)
```

`sold_mbps` is what operators actually retail on each kind of line: 24 for ADSL, 50 for VDSL, 100 for vectored VDSL and 1000 for FTTH. The cap uses the register's *normally available* speed (`a4a_nordown`), which can pull a figure down but never lift it. Mobile and fixed wireless are kept out of street figures, since 5G reaches nearly everything and would paint the whole country one colour.

### Pipeline

Raw register tables land in `raw_*` and are never modified. Everything else is rebuilt by `make build` from re-runnable steps in `normalise/steps/`, in filename order:

| Step | Produces |
|---|---|
| `010` | Municipalities, reprojected to 4326 |
| `020`, `025` | The address index, and filings with no street placed by position |
| `030`, `040` | Point coverage (fiber, coax) and copper cabinet areas |
| `045` | The Telekom scrape, and addresses only it knows |
| `050` | What reaches each address |
| `060`, `065`, `066` | OSM streets, each address pinned to its street, each street's locality |
| `070` | Fixed wireless from the register's 100 m grid |
| `090`, `100` | Wholesale relationships, and fiber built past a door but never filed as a service |
| `110`, `120` | Who reaches each street and its speed |
| `130` | Per-municipality fiber share and measured averages |

A street is reached three ways: doors filed on it, cabinets it runs through, and built fiber beside it. Each step diffs against what it built last time, so an unchanged register rebuilds almost nothing and the same register always builds the same map. Schema changes are checksummed migrations in `normalise/migrations/`, applied by `make migrate`, and can't be edited once applied.

## Getting Started

You need Postgres 18 with PostGIS, Python 3.14 and Node 24. `tippecanoe` is only needed to cut tiles.

```bash
make setup        # .venv, pinned by constraints.txt
make bootstrap    # create the database, migrate, load everything, build
make fonts        # label glyphs, served beside the tiles
make tiles        # cut the map
make api          # http://localhost:8000

cd web
npm install
npm run dev       # http://localhost:5173, proxies /api to :8000
```

`bootstrap` is idempotent and resumable, the register alone takes a few hours. A clone reproduces the register, the streets, the measurements and the tariffs. It does not reproduce two things:

- **The Telekom address scrape** (`data/cosmote.db`), months of asking that a clone can't repeat. The stage is skipped and says what is lost: about 326k addresses, and two checkers that can then only be asked about streets the scrape walked.
- **The basemap and buildings** (`greece.pmtiles`, `buildings.pmtiles`), built with planetiler outside this repo. Without them the map still draws every street, on a bare outline of the country. After copying a build into `tiles/`, `make slim` cuts it down to what the style reads.

## API

FastAPI, read-only apart from reports, asked-for addresses and live probes. The OpenAPI document is generated into `schema/openapi.json`, and the frontend's types are generated from that.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/search` | Addresses and streets, in Greek or Greeklish |
| `GET` | `/addresses/{id}` | One address and everything filed at it |
| `GET` | `/addresses/{id}/options` | What can be bought there, ranked and priced |
| `POST` | `/addresses/{id}/probe` | Asks the operators live |
| `GET` | `/streets/{id}` | One street, its shape and who reaches it |
| `POST` | `/streets/{id}/addresses` | Makes an address the register never filed |
| `POST` | `/reports` | Records that something looks wrong |
| `GET` | `/health`, `/health/adapters` | Row counts, and how each operator's checker is doing |

Search widens in three tiers (prefix, word start, trigram), and the fuzzy tier runs over distinct spellings rather than all 1.8M addresses.

## The Map

MapLibre reading PMTiles by range request, cut by tippecanoe into two archives: `speedmap.pmtiles` with the streets and municipalities, and `cells.pmtiles` with Ookla's measured squares, which only load once someone switches to the measured view. Field names are defined once in `schema/tiles.yaml` and generated into both the Python builder and the TypeScript renderer, so renaming one breaks the build instead of silently drawing nothing.

## Testing

```bash
make check
```

That runs ruff, mypy in strict mode, a lint against substituting numbers for missing values, the generated-file checks, and 223 Python tests against a scratch database built from the migrations. The frontend has 56 tests under Vitest, 13 of which drive a real browser and only run with a dev server on `127.0.0.1:5173` and tiles cut.

`make audit` runs the nine SQL invariants in `tests/invariants/` against the real, built database. The test suite only proves that each of them fires on a planted violation.

CI runs both halves on every push to `main`: the Python job against a PostGIS service container, the web job through typecheck, lint, tests and a production build.

## Development

### Repository Layout

```
ingest/      Register, OSM, Ookla and scrape loaders
normalise/   Migrations, the build steps, Greek text folding and transliteration
probe/       Live operator checkers, the nightly sweep and canaries
prices/      Tariff catalogues
ranking/     Cost, expected speed and ordering
publish/     Tile layers and the tippecanoe cuts
api/         FastAPI app and rate limits
alert/       Push alerts and disk checks
schema/      The tile contract and the OpenAPI document
deploy/      systemd units, Caddyfile and backups for the production host
tools/       Bootstrap, codegen, audit, lints
tests/       pytest suite and SQL invariants
web/         React + MapLibre frontend
```

### Workflow

1. **Branches**: work happens on topic branches off `next`
2. **Checks**: `make check` before anything is merged
3. **CI**: GitHub Actions on `main`
4. **Merge**: `next`, then `main`

All of the site's text lives in `web/src/strings.toml`, Greek and English side by side. `make strings` checks that both languages have the same keys and placeholders and regenerates what the frontend reads. Run `make help` for the rest of the targets.

## Known Limitations

- About 63% of addresses can be pinned to an OSM street. The rest have no matching road of their name.
- A street figure is the best line reaching the street. Distance from the cabinet, and line quality at a particular door, aren't modelled. The measured view is the counterweight.
- The register files ADSL above its physical ceiling on 512 rows, five of them at a gigabit. Those are held to 24 Mbps.
- The Telekom scrape covers 43% of streets, which limits which addresses the Telekom and Nova checkers can be asked about.
- Operators that publish no prices have none here, and where a setup fee is missing the total is a floor.

## License and Attribution

The code is MIT, see [LICENSE](LICENSE). That covers the code only. Every dataset keeps its own terms, and a clone of this repository is not a licence to republish what a build of it produces.

- **OpenStreetMap**, street geometry and the basemap, [ODbL](https://opendatacommons.org/licenses/odbl/): © OpenStreetMap contributors
- **Overture Maps**, building footprints, ODbL: © OpenStreetMap contributors, Overture Maps Foundation, Microsoft, Esri Community Maps contributors, Google Open Buildings
- **Ookla**, measured speeds, [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The non-commercial term binds anything built from the tiles. Ookla specify the wording:

  > Speedtest® by Ookla® Global Fixed and Mobile Network Performance Maps. Based on analysis by Ookla of Speedtest Intelligence® data for Q2 2026. Provided by Ookla and accessed 10 September 2026. Ookla trademarks used under license and reprinted with permission.

- **EETT register**, coverage filings from `broadband-assist.gov.gr`, published by the General Secretariat of Telecommunications and Postal Services. Public, but not open data: its [terms](https://www.broadband-assist.gov.gr/public/terms.html) allow one local copy for personal, non-commercial use with attribution, and prohibit commercial use and modification.
- **Tariffs and checker answers** belong to each operator, are cached only to run the site, and are attributed wherever they appear.
- **Libraries**: [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) (BSD-3), [tippecanoe](https://github.com/felt/tippecanoe) (BSD-2), [planetiler](https://github.com/onthegomap/planetiler) (Apache 2.0), and the [OpenMapTiles fonts](https://github.com/openmaptiles/fonts) (mostly SIL OFL).

The site shows all of this at `/attribution`, generated from `web/src/credits.ts`.
