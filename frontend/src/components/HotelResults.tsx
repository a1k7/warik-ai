import { useState } from 'react';
import {
  ArrowUpRight,
  BedDouble,
  Building2,
  CalendarDays,
  ExternalLink,
  Image as ImageIcon,
  MapPin,
  Moon,
  Star,
  Users,
} from 'lucide-react';
import './hotel-results.css';

type HotelItem = {
  name?: string;
  address?: string;
  price_per_night?: string;
  total_stay?: string;
  currency?: string;
  nights?: number;
  booking_url?: string;
  image_url?: string;
  rating?: string | number;
};

type HotelSearchData = {
  type?: string;
  items?: HotelItem[];
  search_url?: string;
  live_inventory?: boolean;
  resolution_status?: string;
};

const HOTEL_HOSTS = [
  'booking.com',
  'agoda.com',
  'expedia.com',
  'hotels.com',
  'makemytrip.com',
  'goibibo.com',
  'cleartrip.com',
  'airbnb.com',
  'trivago.com',
];

function safeHotelUrl(value?: string): string | null {
  if (!value || value.length > 4096 || /\s/.test(value)) return null;
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase().replace(/\.$/, '');
    const allowed = HOTEL_HOSTS.some((root) => host === root || host.endsWith(`.${root}`));
    return parsed.protocol === 'https:' && allowed ? parsed.href : null;
  } catch {
    return null;
  }
}

function safeImageUrl(value?: string): string | null {
  if (!value || value.length > 4096 || /[\s<>]/.test(value)) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function HotelPhoto({ src, name }: { src?: string; name: string }) {
  const [failed, setFailed] = useState(false);
  const image = safeImageUrl(src);

  if (!image || failed) {
    return (
      <div className="wk-hotel-photo wk-hotel-photo-fallback" aria-label={`Image unavailable for ${name}`}>
        <div className="wk-hotel-fallback-orbit" />
        <div className="wk-hotel-fallback-icon"><Building2 size={27} /></div>
        <span>PROPERTY IMAGE UNAVAILABLE</span>
      </div>
    );
  }

  return (
    <div className="wk-hotel-photo">
      <img
        src={image}
        alt={name}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
      <div className="wk-hotel-photo-shade" />
      <span className="wk-hotel-photo-label"><BedDouble size={12} /> STAY OPTION</span>
    </div>
  );
}

function ratingLabel(value: HotelItem['rating']): string | null {
  if (value === undefined || value === null || String(value).trim() === '') return null;
  return String(value).trim();
}

function HotelCard({ item, index }: { item: HotelItem; index: number }) {
  const bookingUrl = safeHotelUrl(item.booking_url);
  const rating = ratingLabel(item.rating);
  const nights = Number.isFinite(item.nights) && Number(item.nights) > 0 ? Number(item.nights) : null;

  return (
    <article className="wk-hotel-card" style={{ animationDelay: `${index * 70}ms` }}>
      <HotelPhoto src={item.image_url} name={item.name || 'Hotel'} />
      <div className="wk-hotel-card-body">
        <div className="wk-hotel-heading-row">
          <div className="wk-hotel-title-wrap">
            <span className="wk-hotel-eyebrow">ACCOMMODATION</span>
            <h3>{item.name || 'Hotel option'}</h3>
          </div>
          {rating && (
            <div className="wk-hotel-rating" title="Rating supplied by the provider">
              <Star size={13} /> <strong>{rating}</strong>
            </div>
          )}
        </div>

        {item.address && (
          <p className="wk-hotel-address"><MapPin size={13} /><span>{item.address}</span></p>
        )}

        <div className="wk-hotel-meta">
          {nights && <span><Moon size={12} /> {nights} {nights === 1 ? 'night' : 'nights'}</span>}
          {item.currency && <span>{item.currency.toUpperCase()}</span>}
        </div>

        <div className="wk-hotel-price-row">
          <div className="wk-hotel-price-block">
            {item.price_per_night ? (
              <>
                <strong>{item.price_per_night}</strong>
                <span>per night</span>
              </>
            ) : (
              <>
                <strong>Price unavailable</strong>
                <span>Check provider for current rates</span>
              </>
            )}
          </div>
          {item.total_stay && (
            <div className="wk-hotel-total-block">
              <span>TOTAL STAY</span>
              <strong>{item.total_stay}</strong>
            </div>
          )}
        </div>

        {bookingUrl ? (
          <a className="wk-hotel-cta" href={bookingUrl} target="_blank" rel="noopener noreferrer">
            Check availability <ArrowUpRight size={15} />
          </a>
        ) : (
          <div className="wk-hotel-no-link">No validated provider handoff was supplied for this option.</div>
        )}
      </div>
    </article>
  );
}

export function HotelResults({ data }: { data: HotelSearchData }) {
  const items = Array.isArray(data.items) ? data.items : [];
  const searchUrl = safeHotelUrl(data.search_url);

  return (
    <section className="wk-hotel-results" aria-label="Hotel search results">
      <header className="wk-hotel-results-header">
        <div>
          <span className="wk-hotel-results-kicker">STAYS · SEARCH RESULTS</span>
          <h3>Places to stay</h3>
          <p>{items.length > 0 ? `${items.length} option${items.length === 1 ? '' : 's'} returned` : 'No property options were returned'}</p>
        </div>
        <span className={`wk-hotel-source ${data.live_inventory === false ? 'is-handoff' : 'is-provider'}`}>
          <i /> {data.live_inventory === false ? 'SEARCH HANDOFF' : 'RESULTS RECEIVED'}
        </span>
      </header>

      {data.live_inventory === false && (
        <div className="wk-hotel-notice">
          <CalendarDays size={15} />
          <span>Live hotel inventory was unavailable for this request. The provider link below opens a fresh search; no prices or availability are being represented as confirmed.</span>
        </div>
      )}

      {items.length > 0 ? (
        <div className="wk-hotel-grid">
          {items.map((item, index) => (
            <HotelCard key={`${item.name || 'hotel'}-${index}`} item={item} index={index} />
          ))}
        </div>
      ) : (
        <div className="wk-hotel-empty">
          <div><ImageIcon size={20} /></div>
          <strong>No hotel cards to show yet</strong>
          <p>Warik did not receive usable property records. You can still open a provider search to check current rates.</p>
        </div>
      )}

      {searchUrl && (
        <a className="wk-hotel-search-link" href={searchUrl} target="_blank" rel="noopener noreferrer">
          Search more stays with the provider <ExternalLink size={13} />
        </a>
      )}

      <p className="wk-hotel-disclaimer"><Users size={12} /> Provider-returned details can change. Recheck dates, occupancy, total price, cancellation terms and availability on the booking site before proceeding.</p>
    </section>
  );
}
