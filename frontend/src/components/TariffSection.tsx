import type { TariffResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatFinishTime, formatPricePerKwh } from '../utils/format';

/**
 * Octopus dynamic tariff prices: the current half-hourly rate plus the cheapest
 * upcoming slots, so you can see when to charge. Rendered only when on.
 */
export function TariffSection({ data }: { data: TariffResponse }) {
  const current = data.rates[0];
  const currency = data.currency ?? 'GBP';
  // Tick hourly so the "today vs Sat" date label on cheapest slots stays
  // correct over a day boundary without an impure Date.now() in render.
  const now = useNow(3_600_000);

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
