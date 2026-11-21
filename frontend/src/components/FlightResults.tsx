import { useMemo } from 'react';
import {
  ArrowUpRight,
  ExternalLink,
  Info,
  Plane,
  ShieldCheck,
  Ticket,
} from 'lucide-react';
import './flight-results.css';

type FlightSegment = {
  airline?: string;
  flight_number?: string;
  origin?: string;
  destination?: string;
  departure?: string;
  arrival?: string;
  duration_minutes?: number | string;
  duration?: number | string;
};

type FlightItem = {
  price?: string | number;
  currency?: string | null;
  segments?: FlightSegment[];
  stops?: number;
  url?: string;
  booking_url?: string;
  duration_minutes?: number | string;
  duration?: number | string;
  airline?: string;
  flight_number?: string;
};

type Airport = {
  iata?: string;
  name?: string;
  city?: string;
};

type FlightSearchData = {
  type?: string;
  items?: FlightItem[];
  search_url?: string;
  live_inventory?: boolean;
  resolution_status?: string;
  origin?: string;
  destination?: string;
  date?: string;
  departure_date?: string;
  origin_airport?: Airport;
  destination_airport?: Airport;
  origin_airport_candidates?: Airport[];
  destination_airport_candidates?: Airport[];
  source?: string;
};

const BOOKING_HOSTS = [
  'google.com',
  'goindigo.in',
  'airindia.com',
  'akasaair.com',
  'spicejet.com',
  'airvistara.com',
  'airasia.com',
  'makemytrip.com',
  'goibibo.com',
  'cleartrip.com',
  'easemytrip.com',
  'ixigo.com',
  'yatra.com',
  'trip.com',
  'kayak.com',
  'skyscanner.net',
  'skyscanner.co.in',
];

function safeFlightUrl(value?: string): string | null {
  if (!value || value.length > 4096 || /[\s<>]/.test(value)) return null;
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLowerCase().replace(/\.$/, '');
    const allowed = BOOKING_HOSTS.some(
      (root) => hostname === root || hostname.endsWith(`.${root}`),
    );
    return parsed.protocol === 'https:' && allowed ? parsed.href : null;
  } catch {
    return null;
  }
}

function formatTime(value?: string): string {
  if (!value) return '—';
  const text = value.replace('T', ' ').trim();
  const match = text.match(/(?:^|\s)(\d{1,2}:\d{2})(?::\d{2})?/);
  return match ? match[1] : text;
}

function formatDuration(value?: number | string): string | null {
  if (value === undefined || value === null || value === '') return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return String(value);
  const hours = Math.floor(numeric / 60);
  const minutes = numeric % 60;
  return hours ? `${hours}h ${minutes ? `${minutes}m` : ''}`.trim() : `${minutes}m`;
}

function fareNumber(value?: string | number): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const match = value.replace(/,/g, '').match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function FlightCard({ item, index }: { item: FlightItem; index: number }) {
  const segments = Array.isArray(item.segments) ? item.segments : [];
  const first = segments[0] || {};
  const last = segments[segments.length - 1] || first;
  const airline = first.airline || item.airline || 'Airline not supplied';
  const flightNumber = first.flight_number || item.flight_number;
  const stops = typeof item.stops === 'number'
    ? item.stops
    : Math.max(0, segments.length - 1);
  const link = safeFlightUrl(item.url || item.booking_url);
  const duration = formatDuration(item.duration_minutes || item.duration || first.duration_minutes || first.duration);
  const price = item.price !== undefined && item.price !== null && String(item.price).trim()
    ? String(item.price)
    : 'Fare unavailable';
  const currency = item.currency ? String(item.currency).toUpperCase() : '';

  return (
    <article className="wk-flight-card" style={{ animationDelay: `${index * 65}ms` }}>
      <div className="wk-flight-card-top">
        <div className="wk-flight-airline">
          <span className="wk-flight-airline-icon"><Plane size={16} /></span>
          <div>
            <strong>{airline}</strong>
            <span>{flightNumber || 'Flight number not supplied'}</span>
          </div>
        </div>
        <span className="wk-flight-option">OPTION {String(index + 1).padStart(2, '0')}</span>
      </div>

      <div className="wk-flight-route">
        <div className="wk-flight-endpoint">
          <strong>{formatTime(first.departure)}</strong>
          <span>{first.origin || 'Origin'}</span>
        </div>
        <div className="wk-flight-route-middle">
          <span>{duration || 'Duration not supplied'}</span>
          <div className="wk-flight-route-line"><i /><Plane size={13} /><i /></div>
          <span>{stops === 0 ? 'NON-STOP' : `${stops} STOP${stops === 1 ? '' : 'S'}`}</span>
        </div>
        <div className="wk-flight-endpoint is-arrival">
          <strong>{formatTime(last.arrival)}</strong>
          <span>{last.destination || 'Destination'}</span>
        </div>
      </div>

      {segments.length > 1 && (
        <div className="wk-flight-connection-note">
          {segments.map((segment, segmentIndex) => (
            <span key={`${segment.flight_number || 'leg'}-${segmentIndex}`}>
              {segment.airline || 'Flight'} {segment.flight_number || ''}
              {segmentIndex < segments.length - 1 ? '  ·  ' : ''}
            </span>
          ))}
        </div>
      )}

      <div className="wk-flight-card-bottom">
        <div className="wk-flight-fare">
          <span>DISPLAYED FARE</span>
          <strong>{price}</strong>
          {currency && <small>{currency}</small>}
        </div>
        {link ? (
          <a className="wk-flight-cta" href={link} target="_blank" rel="noopener noreferrer">
            Check flight <ArrowUpRight size={15} />
          </a>
        ) : (
          <span className="wk-flight-no-link">No verified provider link</span>
        )}
      </div>
    </article>
  );
}

export function FlightResults({ data }: { data: FlightSearchData }) {
  const items = Array.isArray(data.items) ? data.items : [];
  const originAirport = data.origin_airport || data.origin_airport_candidates?.[0];
  const destinationAirport = data.destination_airport || data.destination_airport_candidates?.[0];
  const searchUrl = safeFlightUrl(data.search_url);
  const routeLabel = [
    originAirport?.iata || data.origin || 'Departure',
    destinationAirport?.iata || data.destination || 'Arrival',
  ].join(' → ');
  const dateLabel = data.departure_date || data.date;
  const allComparable = items.length > 1 && items.every((item) =>
    item.currency && item.currency === items[0].currency && fareNumber(item.price) !== null,
  );
  const orderedItems = useMemo(() => {
    if (!allComparable) return items;
    return [...items].sort((a, b) => (fareNumber(a.price) ?? Infinity) - (fareNumber(b.price) ?? Infinity));
  }, [allComparable, items]);

  return (
    <section className="wk-flight-results" aria-label="Flight search results">
      <header className="wk-flight-results-header">
        <div>
          <span className="wk-flight-kicker">FLIGHTS · SEARCH RESULTS</span>
          <h3>Compare your flight options</h3>
          <p>{routeLabel}{dateLabel ? ` · ${dateLabel}` : ''}</p>
        </div>
        <span className={`wk-flight-source ${data.live_inventory === false ? 'is-handoff' : 'is-results'}`}>
          <i />{data.live_inventory === false ? 'SEARCH HANDOFF' : 'OPTIONS RETURNED'}
        </span>
      </header>

      {(originAirport || destinationAirport) && (
        <div className="wk-flight-airport-strip">
          <div><span>FROM</span><strong>{originAirport?.iata || '—'}</strong><small>{originAirport?.name || originAirport?.city || 'Airport not resolved'}</small></div>
          <Plane size={16} />
          <div><span>TO</span><strong>{destinationAirport?.iata || '—'}</strong><small>{destinationAirport?.name || destinationAirport?.city || 'Airport not resolved'}</small></div>
        </div>
      )}

      {data.live_inventory === false && (
        <div className="wk-flight-notice"><Info size={15} /><span>Live flight inventory was not returned for this request. The external link opens a fresh search; no schedule, seat or fare is represented as confirmed.</span></div>
      )}

      {orderedItems.length ? (
        <div className="wk-flight-list">
          {orderedItems.map((item, index) => <FlightCard key={`${item.url || item.booking_url || 'flight'}-${index}`} item={item} index={index} />)}
        </div>
      ) : (
        <div className="wk-flight-empty">
          <div><Ticket size={21} /></div>
          <strong>No flight options returned</strong>
          <p>Warik did not receive usable flight records. You can still check the route directly with a search provider.</p>
        </div>
      )}

      {searchUrl && (
        <a className="wk-flight-search-link" href={searchUrl} target="_blank" rel="noopener noreferrer">
          Search this route with the provider <ExternalLink size={13} />
        </a>
      )}

      <p className="wk-flight-disclaimer"><ShieldCheck size={12} /> Fares and schedules can change. Verify baggage, cancellation terms, passenger details and final price with the airline or booking provider before purchasing.</p>
    </section>
  );
}
