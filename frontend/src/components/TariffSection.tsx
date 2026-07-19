import type { TariffResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatFinishTime, formatPricePerKwh } from '../utils/format';

/**
 * Octopus tariff prices: the current rate plus the cheapest upcoming slots, so
 * you can see when to charge. Rendered only when configured.
 */
export function TariffSection({ data }: { data: TariffResponse }) {
  const currency = data.currency ?? 'GBP';
  // Tick each minute so "Now" rolls to the next half-hour slot, and the
  // "today vs Sat" date label on cheapest slots stays correct over a day
  // boundary, without an impure Date.now() in render.
  const now = useNow(60_000);
  // The in-effect slot is the one whose window contains `now` — don't assume
  // rates[0] is current (the list may start with a not-yet-current slot). Fall
  // back to the first upcoming slot if none currently applies.
  const current =
    data.rates.find((r) => {
      const from = new Date(r.from).getTime();
      const to = r.to ? new Date(r.to).getTime() : Infinity;
      return from <= now && now < to;
    }) ?? data.rates[0];

  return (
    <section className="card tariff-card" aria-labelledby="tariff-heading">
      <header>
        <div>
          <p className="eyebrow">Tariff</p>
          <h2 id="tariff-heading">Upcoming prices</h2>
        </div>
        {current && (
          <div className="tariff-now">
            <span className="label">Now</span>
            <span className="price">{formatPricePerKwh(current.pricePerKwh, currency)}</span>
          </div>
        )}
      </header>

      {data.cheapest.length > 0 ? (
        <>
          <p className="tariff-subhead">Cheapest upcoming</p>
          <ul className="tariff-cheapest">
            {data.cheapest.map((rate) => (
              <li key={rate.from}>
                <span className="time">{formatFinishTime(rate.from, new Date(now))}</span>
                <span className="price">{formatPricePerKwh(rate.pricePerKwh, currency)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="tariff-empty">No upcoming rates available.</p>
      )}
    </section>
  );
}
