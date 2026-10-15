// Routers to suggest where mobile beats the wire, one per situation, picked by hand. Plain
// links, the site earns nothing (non-commercial data terms). No prices, Skroutz's change daily.

export type Router = {
  // key into [el.routerWhy] and [el.routerFor]
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
