/**
 * The routers the site suggests where a mobile connection beats the wire. Picked by hand, one
 * per situation, and linked plainly: the site earns nothing from a sale, which keeps it inside
 * the non-commercial terms its data comes under.
 *
 * No prices. Skroutz's change daily and a stale one is worse than none, so the link shows them.
 * Why each one is here, and everything else a reader sees, is in strings.toml.
 */

export type Router = {
  /** key into [el.routerWhy] and [el.routerFor] */
  readonly id: string;
  readonly name: string;
  readonly href: string;
};

export const ROUTERS: readonly Router[] = [
  {
    id: "mc888",
    name: "ZTE MC888",
    href: "https://www.skroutz.gr/s/41669191/ZTE-MC888-Asyrmato-5G-Router-Wi-Fi-6-me-2-THyres.html",
  },
  {
    id: "nx600",
    name: "TP-Link Archer NX600",
    href: "https://www.skroutz.gr/s/58957405/TP-LINK-Archer-NX600-v1-Asyrmato-5G-Router-Wi-Fi-6-me-3-THyres-Gigabit.html",
  },
  {
    id: "mr600",
    name: "TP-Link Archer MR600 v5",
    href: "https://www.skroutz.gr/s/61482347/tp-link-archer-mr600-v5-asyrmato-4g-router-wi-fi-5-me-4-thyres.html",
  },
  {
    id: "nr7101",
    name: "Zyxel NR7101",
    href: "https://www.skroutz.gr/s/40892852/Zyxel-NR7101-Asyrmato-5G-Mobile-Router.html",
  },
];
