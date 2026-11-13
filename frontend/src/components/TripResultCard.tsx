import {
  Plane,
  Building2,
  Car,
  MapPin,
  ExternalLink,
  AlertTriangle,
  ArrowRight,
  Map,
  Clock,
  CalendarDays,
  Sparkles,
  Image as ImageIcon,
} from 'lucide-react';
import { useState } from 'react';

interface TripData {
  type: 'trip_summary';
  destination: string;
  flights: any[];
  hotels: any[];
  cabs: any;
  itinerary: any;
  failures: any[];
}

function HotelImage({ src, name }: { src?: string; name: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="h-48 w-full bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex flex-col items-center justify-center gap-2">
        <ImageIcon size={28} className="text-[#C99AA4]/60" />
        <span className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4]/60">
          Image unavailable
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-48 w-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
    />
  );
}

function ActivityImage({ activity }: { activity: any }) {
  const [failed, setFailed] = useState(false);

  if (failed || !activity.image_url) {
    return (
      <div className="h-32 sm:h-40 bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex items-center justify-center">
        <ImageIcon size={24} className="text-[#C99AA4]/60" />
      </div>
    );
  }

  return (
    <div>
      <img
        src={activity.image_url}
        alt={activity.name}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="h-40 sm:h-48 w-full object-cover"
      />
      {(activity.image_credit || activity.image_source_url) && (
        <div className="px-3 py-2 flex justify-between items-center gap-2 bg-black/20">
          <span className="text-[10px] text-[#BCA7AF] truncate">
            {activity.image_credit || "Image source"}
          </span>
          {activity.image_source_url && (
            <a
              href={activity.image_source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-[#D6A8B3] shrink-0 hover:text-white"
            >
              Source ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function ActivityGroup({
  label,
  activities,
}: {
  label: string;
  activities: any[];
}) {
  if (!activities?.length) return null;

  return (
    <div className="flex gap-3">
      <div className="w-1 rounded-full bg-[#A96C7C]/50 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-semibold mb-2">
          {label}
        </p>
        <div className="grid gap-2">
          {activities.map((activity, index) => (
            <div
              key={`${label}-${index}`}
              className="rounded-xl bg-white/[0.035] border border-white/[0.055] overflow-hidden"
            >
              {activity.image_url ? (
                <ActivityImage activity={activity} />
              ) : (
                <div className="h-32 sm:h-40 bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex items-center justify-center">
                  <div className="text-center">
                    <ImageIcon size={24} className="text-[#C99AA4]/60 mx-auto mb-2" />
                    <span className="text-[9px] uppercase tracking-[0.2em] text-[#C99AA4]/60">
                      Photo unavailable
                    </span>
                  </div>
                </div>
              )}
              <div className="p-3">
              <div className="flex items-start gap-2">
                <Clock size={13} className="text-[#C99AA4] mt-1 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm text-[#FAF7F3] font-medium">
                    {activity.name}
                  </p>
                  {activity.suggested_time && (
                    <p className="text-xs text-[#BCA7AF] mt-1">
                      {activity.suggested_time}
                    </p>
                  )}
                  {activity.description && (
                    <p className="text-xs text-[#BCA7AF]/80 mt-1 leading-relaxed">
                      {activity.description}
                    </p>
                  )}
                  {activity.map_url && (
                    <a
                      href={activity.map_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-[#D6A8B3] mt-2 hover:text-white"
                    >
                      Explore location <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export const TripResultCard = ({ data }: { data: TripData }) => {
  if (!data) return null;

  const hotels = data.hotels || [];
  const days = data.itinerary?.days || [];

  const displayTitle =
    !data.destination || data.destination === 'Your Trip'
      ? 'Your Travel Plan'
      : data.destination;

  return (
    <div className="w-full flex flex-col gap-5 mt-5 text-[#FAF7F3] animate-in fade-in slide-in-from-bottom-4 duration-500">

      {/* DESTINATION HERO */}
      <section className="relative overflow-hidden rounded-[24px] border border-[#B77B89]/30 bg-gradient-to-br from-[#702D3C] via-[#452331] to-[#171319] shadow-2xl">
        <div className="absolute -right-12 -top-16 w-64 h-64 rounded-full border border-white/[0.08]" />
        <div className="absolute -right-4 -top-8 w-44 h-44 rounded-full border border-white/[0.08]" />
        <div className="absolute right-8 bottom-[-90px] w-56 h-56 rounded-full bg-[#D3A1AD]/10 blur-3xl" />

        <div className="relative z-10 p-6 sm:p-8">
          <div className="flex justify-between items-start gap-4">
            <div>
              <div className="flex items-center gap-2 text-[#E6BAC4] text-[10px] font-bold tracking-[0.25em] uppercase mb-4">
                <Sparkles size={13} />
                Curated by Warik
              </div>

              <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
                {displayTitle}
              </h2>

              <p className="text-[#E8C9D0]/80 text-sm mt-2">
                Your journey, thoughtfully put together.
              </p>
            </div>

            <span className="shrink-0 rounded-full border border-white/20 bg-black/15 px-3 py-2 text-[10px] uppercase tracking-wider text-[#F6DDE3]">
              {data.failures?.length ? 'Partially ready' : 'Plan ready'}
            </span>
          </div>

          <div className="flex flex-wrap gap-4 mt-7 pt-5 border-t border-white/15">
            {data.itinerary?.travellers && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Travellers
                </span>
                {data.itinerary.travellers} people
              </div>
            )}
            {days.length > 0 && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Duration
                </span>
                {days.length} days
              </div>
            )}
            {hotels.length > 0 && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Stays found
                </span>
                {hotels.length} options
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ITINERARY */}
      {days.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div>
              <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
                <Map size={14} /> Your journey
              </div>
              <h3 className="text-xl font-semibold mt-1">Day by day</h3>
            </div>
            <CalendarDays className="text-[#C99AA4]" size={22} />
          </div>

          <div className="flex flex-col gap-4">
            {days.map((day: any) => (
              <article
                key={day.day}
                className="rounded-2xl border border-white/[0.07] bg-[#1A1417] overflow-hidden"
              >
                <div className="p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-bold">
                        Day {day.day}
                      </p>
                      <h4 className="text-base font-semibold mt-1">
                        {day.title?.replace(/^Day\s*\d+\s*[—-]?\s*/i, '') || `Day ${day.day}`}
                      </h4>
                    </div>
                    {day.date && (
                      <span className="text-xs text-[#BCA7AF] shrink-0">
                        {day.date}
                      </span>
                    )}
                  </div>

                  <div className="grid gap-4">
                    <ActivityGroup label="Morning" activities={day.morning} />
                    <ActivityGroup label="Afternoon" activities={day.afternoon} />
                    <ActivityGroup label="Evening" activities={day.evening} />
                  </div>

                  {day.meal_suggestions?.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/[0.07]">
                      <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-semibold mb-2">
                        Food suggestions
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {day.meal_suggestions.map((meal: any, i: number) => (
                          <span
                            key={i}
                            className="rounded-full border border-[#A96C7C]/30 bg-[#702D3C]/20 px-3 py-1.5 text-xs text-[#F1DDE2]"
                          >
                            {meal.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* HOTELS */}
      {hotels.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="mb-5">
            <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
              <Building2 size={14} /> Handpicked stays
            </div>
            <h3 className="text-xl font-semibold mt-1">Places to stay</h3>
            <p className="text-xs text-[#BCA7AF] mt-1">
              Compare available properties and booking options.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {hotels.map((hotel: any, index: number) => (
              <article
                key={`${hotel.name}-${index}`}
                className="group overflow-hidden rounded-2xl border border-white/[0.08] bg-[#1A1417] hover:border-[#C99AA4]/40 transition-all duration-300"
              >
                <div className="overflow-hidden">
                  <HotelImage src={hotel.image_url} name={hotel.name} />
                </div>

                <div className="p-4">
                  <div className="flex justify-between items-start gap-3">
                    <div className="min-w-0">
                      <h4 className="font-semibold text-[#FAF7F3] leading-snug">
                        {hotel.name}
                      </h4>
                      {(hotel.city || hotel.address) && (
                        <p className="flex items-start gap-1.5 text-xs text-[#BCA7AF] mt-2">
                          <MapPin size={12} className="mt-0.5 shrink-0" />
                          {hotel.city || hotel.address}
                        </p>
                      )}
                    </div>

                    {hotel.rating && hotel.rating !== 'Not provided' && (
                      <span className="shrink-0 rounded-lg bg-[#B88A4A]/15 border border-[#B88A4A]/20 px-2 py-1 text-xs text-[#E6C58D]">
                        ★ {hotel.rating}
                      </span>
                    )}
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/[0.07] pt-3">
                    <div>
                      <p className="text-[9px] uppercase tracking-wider text-[#A98D98]">
                        Total stay
                      </p>
                      <p className="text-base font-semibold mt-1">
                        {hotel.price || hotel.total_stay || 'Price unavailable'}
                      </p>
                    </div>
                    <div>
                      <p className="text-[9px] uppercase tracking-wider text-[#A98D98]">
                        Per night
                      </p>
                      <p className="text-sm font-medium mt-1">
                        {hotel.price_per_night || 'Not available'}
                      </p>
                    </div>
                  </div>

                  {(hotel.check_in || hotel.check_out) && (
                    <p className="text-[11px] text-[#BCA7AF] mt-3">
                      {hotel.check_in || 'Check-in unavailable'} → {hotel.check_out || 'Check-out unavailable'}
                    </p>
                  )}

                  {hotel.booking_url && (
                    <a
                      href={hotel.booking_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-4 flex items-center justify-center gap-2 w-full rounded-xl bg-[#702D3C] hover:bg-[#873D50] py-3 text-xs font-semibold text-white transition-colors"
                    >
                      View booking options <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* FLIGHTS */}
      {data.flights?.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold mb-1">
            <Plane size={14} /> Flight options
          </div>
          <h3 className="text-xl font-semibold mb-4">Getting there</h3>

          <div className="grid gap-3">
            {data.flights.map((flight: any, index: number) => (
              <article
                key={index}
                className="rounded-xl bg-[#1A1417] border border-white/[0.07] p-4"
              >
                <div className="flex items-center justify-between gap-3 mb-3">
                  <p className="text-lg font-semibold">{flight.price}</p>
                  <span className="text-xs text-[#D6A8B3]">
                    {flight.stops === 0 ? 'Non-stop' : `${flight.stops ?? '—'} stop(s)`}
                  </span>
                </div>

                {flight.segments?.map((segment: any, j: number) => (
                  <div key={j} className="border-t border-white/[0.07] pt-3 mt-2">
                    <div className="flex justify-between text-sm gap-2">
                      <span className="font-medium">
                        {segment.airline} {segment.flight_number}
                      </span>
                      <span className="text-[#C99AA4] text-xs">
                        {segment.departure}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[#BCA7AF] mt-2">
                      <span>{segment.origin}</span>
                      <ArrowRight size={12} />
                      <span>{segment.destination}</span>
                      <span className="ml-auto">{segment.arrival}</span>
                    </div>
                  </div>
                ))}

                {flight.url && (
                  <a
                    href={flight.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-4 flex justify-center items-center gap-2 rounded-xl bg-[#702D3C] hover:bg-[#873D50] py-2.5 text-xs font-semibold"
                  >
                    View flight <ExternalLink size={12} />
                  </a>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {/* TRANSPORT */}
      {data.cabs && Object.keys(data.cabs).length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
            <Car size={14} /> Ground transport
          </div>
          <h3 className="text-xl font-semibold mt-1 mb-4">Continue your journey</h3>

          <div className="flex flex-wrap gap-2">
            {Object.entries(data.cabs).map(([key, url]: [string, any]) => (
              <a
                key={key}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#1A1417] px-4 py-3 text-sm capitalize hover:border-[#C99AA4]/50 transition-colors"
              >
                {key} <ExternalLink size={13} />
              </a>
            ))}
          </div>
        </section>
      )}

      {/* FAILURES */}
      {data.failures?.length > 0 && (
        <section className="rounded-2xl border border-amber-500/20 bg-amber-950/20 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-300">
            <AlertTriangle size={16} />
            Some services need attention
          </p>
          {data.failures.map((failure: any, index: number) => (
            <p key={index} className="text-xs text-amber-100/70 mt-2">
              {failure.tool}: {failure.error}
            </p>
          ))}
        </section>
      )}
    </div>
  );
};