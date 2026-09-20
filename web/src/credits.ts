/**
 * Who made the data under the map.
 */

export type Credit = {
  readonly id: string;
  readonly name: string;
  readonly href: string;
  readonly licence: string;
  readonly licenceHref: string;
  readonly line: string;
};

export const SOURCES: readonly Credit[] = [
  {
    id: "osm",
    name: "OpenStreetMap",
    href: "https://www.openstreetmap.org/",
    licence: "ODbL 1.0",
    licenceHref: "https://opendatacommons.org/licenses/odbl/",
    line: "© OpenStreetMap contributors",
  },
  {
    id: "overture",
    name: "Overture Maps Foundation",
    href: "https://overturemaps.org/",
    licence: "ODbL 1.0",
    licenceHref: "https://opendatacommons.org/licenses/odbl/",
    line:
      "© OpenStreetMap contributors, Overture Maps Foundation, Microsoft, " +
      "Esri Community Maps contributors, Google Open Buildings",
  },
  {
    id: "ookla",
    name: "Ookla",
    href: "https://www.ookla.com/ookla-for-good/open-data",
    licence: "CC BY-NC-SA 4.0",
    licenceHref: "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    line:
      "Speedtest® by Ookla® Global Fixed and Mobile Network Performance Maps. " +
      "Based on analysis by Ookla of Speedtest Intelligence® data for Q2 2026. " +
      "Provided by Ookla and accessed 10 September 2026. " +
      "Ookla trademarks used under license and reprinted with permission.",
  },
  {
    id: "eett",
    name: "ΕΕΤΤ / ΓΓΤΤ",
    href: "https://www.broadband-assist.gov.gr/",
    licence: "broadband-assist.gov.gr",
    licenceHref: "https://www.broadband-assist.gov.gr/public/terms.html",
    line: "Χάρτης Ευρυζωνικής Μηχανογραφημένης Διάθεσης, Γενική Γραμματεία Τηλεπικοινωνιών και Ταχυδρομείων",
  },
];

/** The things the map is drawn with, as opposed to the things it draws. */
export const TOOLS: readonly Credit[] = [
  {
    id: "maplibre",
    name: "MapLibre GL JS",
    href: "https://github.com/maplibre/maplibre-gl-js",
    licence: "BSD 3-Clause",
    licenceHref: "https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt",
    line: "",
  },
  {
    id: "glyphs",
    name: "OpenMapTiles fonts",
    href: "https://github.com/openmaptiles/fonts",
    licence: "SIL OFL 1.1",
    licenceHref: "https://openfontlicense.org/",
    line: "",
  },
  {
    id: "planetiler",
    name: "Planetiler",
    href: "https://github.com/onthegomap/planetiler",
    licence: "Apache 2.0",
    licenceHref: "https://www.apache.org/licenses/LICENSE-2.0",
    line: "",
  },
  {
    id: "tippecanoe",
    name: "Tippecanoe",
    href: "https://github.com/felt/tippecanoe",
    licence: "BSD 2-Clause",
    licenceHref: "https://github.com/felt/tippecanoe/blob/main/LICENSE.md",
    line: "",
  },
];
