/**
 * An operator's own mark, or their initial when they have none. This is a page people scan
 * rather than read, and a logo is recognised before a name is.
 */

import { brandOf } from "../brands";

export function Logo({ provider }: { readonly provider: string }): React.ReactElement {
  const brand = brandOf(provider);
  if (brand.mark === null) {
    return (
      <span className="logo logo-initial" style={{ color: brand.colour }} aria-hidden="true">
        {provider.slice(0, 1)}
      </span>
    );
  }
  return <img className="logo" src={brand.mark} alt="" aria-hidden="true" />;
}
