// an operator's mark, or their initial

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
