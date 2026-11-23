import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowDownUp, ArrowRight, CarFront, CheckCircle2, Clock3, ExternalLink,
  Luggage, MapPin, MessageCircle, Navigation, Send, ShieldCheck, Users, XCircle,
} from 'lucide-react';
import { createConversation, fetchConversationDetail, sendMessageInConversation } from './api';

type CabStructuredData = {
  type?: string;
  origin?: string;
  destination?: string;
  pickup_at?: string | null;
  passengers?: number;
  vehicle_preference?: string;
  luggage_count?: number;
  links?: Record<string, string>;
  live_quote?: boolean;
  booking_created?: boolean;
  payment_processed?: boolean;
  disclaimer?: string;
};
type CabMessage = {
  id: number | string;
  role: 'user' | 'assistant';
  content: string;
  structured_data?: CabStructuredData | null;
};

const providerHosts: Record<string, string[]> = {
  uber: ['m.uber.com', 'uber.com'],
  ola: ['book.olacabs.com', 'olacabs.com'],
};

function toLocalDateTimeInput(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}
function safeProviderUrl(provider: string, value: string): string | null {
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'https:') return null;
    const allowed = providerHosts[provider.toLowerCase()] || [];
    return allowed.some((host) => parsed.hostname === host || parsed.hostname.endsWith('.' + host))
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function ProviderOptions({ data }: { data: CabStructuredData }) {
  const providers = Object.entries(data.links || {})
    .map(([provider, url]) => ({ provider: provider.toLowerCase(), url: safeProviderUrl(provider, url) }))
    .filter((item): item is { provider: string; url: string } => Boolean(item.url));
  if (!providers.length) return null;

  return (
    <section className="cab-provider-section" aria-label="Ride provider handoff options">
      <div className="cab-section-title-row">
        <div><span className="cab-eyebrow">PROVIDER HANDOFF</span><h3>Continue with a ride provider</h3></div>
        <span className="cab-route-ready"><CheckCircle2 size={13} /> Route prepared</span>
      </div>
      <div className="cab-provider-grid">
        {providers.map(({ provider, url }) => (
          <article className={'cab-provider-card cab-provider-' + provider} key={provider}>
            <div className="cab-provider-top">
              <span className="cab-provider-mark">{provider === 'uber' ? 'U' : 'O'}</span>
              <span className="cab-provider-name">{provider === 'uber' ? 'Uber' : provider === 'ola' ? 'Ola' : provider}</span>
              <span className="cab-prefill-tag">Route prefilled</span>
            </div>
            <div className="cab-provider-price"><strong>Check live fare</strong><span>Shown in provider app</span></div>
            <a href={url} target="_blank" rel="noopener noreferrer" className="cab-provider-cta">
              Continue to {provider === 'uber' ? 'Uber' : provider === 'ola' ? 'Ola' : provider}<ExternalLink size={15} />
            </a>
          </article>
        ))}
      </div>
      <div className="cab-preference-summary">
        <span>REQUESTED · VERIFY IN APP</span>
        <div>
          <b>{data.pickup_at === 'now' ? 'As soon as possible' : data.pickup_at ? 'Scheduled · ' + data.pickup_at.replace('T', ' ') : 'Pickup time to confirm'}</b>
          <b>{data.passengers || 1} {(data.passengers || 1) === 1 ? 'passenger' : 'passengers'}</b>
          <b>{(data.vehicle_preference || 'any') === 'any' ? 'Any vehicle' : (data.vehicle_preference || '').toUpperCase()}</b>
          <b>{data.luggage_count || 0} {(data.luggage_count || 0) === 1 ? 'bag' : 'bags'}</b>
        </div>
      </div>
      <div className="cab-provider-disclaimer"><ShieldCheck size={15} /><p>{data.disclaimer || 'The handoff pre-fills your route. Check the final fare, vehicle, pickup time and availability in the provider app. No ride has been booked and no payment has been made.'}</p></div>
    </section>
  );
}

export function CabWorkspace() {
  const conversationRef = useRef<number | null>(null);
  const [pickup, setPickup] = useState('');
  const [dropoff, setDropoff] = useState('');
  const [scheduleMode, setScheduleMode] = useState<'now' | 'later'>('now');
  const [pickupAt, setPickupAt] = useState('');
  const [passengers, setPassengers] = useState(1);
  const [vehicle, setVehicle] = useState('any');
  const [luggage, setLuggage] = useState(0);
  const [messages, setMessages] = useState<CabMessage[]>([]);
  const [assistantInput, setAssistantInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [lastRoute, setLastRoute] = useState<{ pickup: string; dropoff: string } | null>(null);

  const ensureConversation = async () => {
    if (conversationRef.current) return conversationRef.current;
    const storedId = Number(localStorage.getItem('warik_cab_conversation_id'));
    if (Number.isInteger(storedId) && storedId > 0) {
      try {
        const detail = await fetchConversationDetail(storedId);
        const restored = (detail.messages || []).map((message: any) => ({
          id: message.id,
          role: message.role === 'user' ? 'user' : 'assistant',
          content: String(message.content || ''),
          structured_data: message.structured_data || null,
        })) as CabMessage[];
        conversationRef.current = storedId;
        setMessages(restored);
        const lastAssistant = [...restored].reverse().find((message) => message.role === 'assistant' && message.structured_data?.type === 'transport_links');
        if (lastAssistant?.structured_data) {
          setLastRoute({
            pickup: lastAssistant.structured_data.origin || '',
            dropoff: lastAssistant.structured_data.destination || '',
          });
        }
        return storedId;
      } catch {
        localStorage.removeItem('warik_cab_conversation_id');
      }
    }
    const created = await createConversation();
    conversationRef.current = created.id;
    localStorage.setItem('warik_cab_conversation_id', String(created.id));
    return created.id;
  };

  const sendToWarik = async (text: string, route?: { pickup: string; dropoff: string }) => {
    setError('');
    setBusy(true);
    const temporaryId = Date.now();
    let userMessageAdded = false;
    try {
      // Restore/create the conversation before optimistic rendering so the
      // restored history cannot overwrite the outgoing message.
      const conversationId = await ensureConversation();
      setMessages((current) => [...current, { id: temporaryId, role: 'user', content: text }]);
      userMessageAdded = true;
      const response = await sendMessageInConversation(conversationId, text);
      const assistantMessage: CabMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.reply || 'I could not prepare that ride request. Please check the details and try again.',
        structured_data: response.structured_data || null,
      };
      setMessages((current) => [...current, assistantMessage]);
      if (assistantMessage.structured_data?.type === 'transport_links') {
        setLastRoute({
          pickup: assistantMessage.structured_data.origin || route?.pickup || '',
          dropoff: assistantMessage.structured_data.destination || route?.dropoff || '',
        });
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Warik could not reach the cab service. Check that the backend is running and try again.');
      if (userMessageAdded) {
        setMessages((current) => current.filter((message) => message.id !== temporaryId));
      }
    } finally {
      setBusy(false);
    }
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const from = pickup.trim();
    const to = dropoff.trim();
    if (!from || !to) {
      setFormError('Enter both a pickup and a drop-off location to prepare your ride.');
      return;
    }
    if (from.toLowerCase() === to.toLowerCase()) {
      setFormError('Pickup and drop-off must be different locations.');
      return;
    }
    if (scheduleMode === 'later' && !pickupAt) {
      setFormError('Choose the date and time for your scheduled pickup.');
      return;
    }
    setFormError('');
    const requestedTime = scheduleMode === 'now' ? 'now' : pickupAt;
    const request = [
      'Book a cab from ' + from + ' to ' + to,
      'pickup_at=' + requestedTime,
      'passengers=' + passengers,
      'vehicle_preference=' + vehicle,
      'luggage_count=' + luggage,
    ].join(' | ');
    setLastRoute({ pickup: from, dropoff: to });
    void sendToWarik(request, { pickup: from, dropoff: to });
  };

  const submitAssistantMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = assistantInput.trim();
    if (!text || busy) return;
    setAssistantInput('');
    const request = /\b(cab|taxi|uber|ola|ride)\b/i.test(text) ? text : 'Cab request: ' + text;
    void sendToWarik(request);
  };

  const swapLocations = () => {
    setPickup(dropoff);
    setDropoff(pickup);
  };
  const mapUrl = lastRoute
    ? 'https://www.google.com/maps/dir/?api=1&origin=' + encodeURIComponent(lastRoute.pickup) + '&destination=' + encodeURIComponent(lastRoute.dropoff)
    : null;

  return (
    <div className="cab-workspace">
      <header className="cab-page-heading">
        <div>
          <span className="cab-eyebrow"><i /> WARIK MOBILITY</span>
          <h1>Your next ride, <em>handled.</em></h1>
          <p>Tell Warik where you are going. Compare provider handoffs and approve the ride in the app you trust.</p>
        </div>
        <div className="cab-approval-pill"><ShieldCheck size={16} /> You approve every booking</div>
      </header>

      <div className="cab-main-grid">
        <section className="cab-search-card">
          <div className="cab-card-heading">
            <div><span className="cab-step-label">01 / RIDE DETAILS</span><h2>Where do you need to go?</h2><p>Set your route and preferences. Warik keeps them with the request.</p></div>
            <span className="cab-heading-icon"><CarFront size={21} /></span>
          </div>
          <form onSubmit={submitSearch} className="cab-search-form">
            <div className="cab-route-inputs">
              <label className="cab-location-field">
                <span className="cab-location-dot pickup-dot" />
                <span className="cab-field-copy"><small>PICKUP LOCATION</small><input value={pickup} onChange={(event) => setPickup(event.target.value)} placeholder="Enter pickup point" autoComplete="street-address" /></span>
              </label>
              <button type="button" className="cab-swap-button" onClick={swapLocations} aria-label="Swap pickup and drop-off"><ArrowDownUp size={16} /></button>
              <label className="cab-location-field">
                <span className="cab-location-dot dropoff-dot" />
                <span className="cab-field-copy"><small>DROP-OFF LOCATION</small><input value={dropoff} onChange={(event) => setDropoff(event.target.value)} placeholder="Where to?" autoComplete="off" /></span>
              </label>
            </div>

            <div className="cab-schedule-row">
              <div className="cab-segmented-control" role="group" aria-label="Pickup time">
                <button type="button" className={scheduleMode === 'now' ? 'selected' : ''} onClick={() => setScheduleMode('now')}><Clock3 size={14} /> Now</button>
                <button type="button" className={scheduleMode === 'later' ? 'selected' : ''} onClick={() => setScheduleMode('later')}>Schedule</button>
              </div>
              {scheduleMode === 'later' && (
                <label className="cab-scheduled-field"><span>Pickup date & time</span><input type="datetime-local" value={pickupAt} onChange={(event) => setPickupAt(event.target.value)} min={toLocalDateTimeInput(new Date(Date.now() + 60000))} /></label>
              )}
            </div>

            <div className="cab-preferences">
              <label><span><Users size={14} /> PASSENGERS</span><select value={passengers} onChange={(event) => setPassengers(Number(event.target.value))}>{[1, 2, 3, 4, 5, 6, 7, 8].map((count) => <option value={count} key={count}>{count} {count === 1 ? 'passenger' : 'passengers'}</option>)}</select></label>
              <label><span><CarFront size={14} /> VEHICLE TYPE</span><select value={vehicle} onChange={(event) => setVehicle(event.target.value)}><option value="any">Any available</option><option value="mini">Mini</option><option value="sedan">Sedan</option><option value="suv">SUV</option><option value="premium">Premium</option></select></label>
              <label><span><Luggage size={14} /> LUGGAGE</span><select value={luggage} onChange={(event) => setLuggage(Number(event.target.value))}>{[0, 1, 2, 3, 4, 5, 6, 7, 8].map((count) => <option value={count} key={count}>{count} {count === 1 ? 'bag' : 'bags'}</option>)}</select></label>
            </div>
            {formError && <p className="cab-inline-error"><XCircle size={15} /> {formError}</p>}
            <button className="cab-search-button" type="submit" disabled={busy}>{busy ? 'Preparing your ride…' : 'Find ride options'} <ArrowRight size={17} /></button>
            <p className="cab-form-footnote"><ShieldCheck size={13} /> Searching never books a ride or charges you.</p>
          </form>
        </section>

        <aside className="cab-route-panel">
          <div className="cab-route-panel-top"><span className="cab-step-label">ROUTE PREVIEW</span><span className="cab-map-chip"><Navigation size={12} /> MAP HANDOFF</span></div>
          <div className="cab-illustrative-map" aria-label="Illustrative route preview, not live navigation">
            <div className="cab-map-road cab-map-road-a" /><div className="cab-map-road cab-map-road-b" /><div className="cab-map-road cab-map-road-c" /><div className="cab-map-road cab-map-road-d" />
            <svg viewBox="0 0 420 275" role="presentation" className="cab-map-path"><path d="M78 67 L132 93 L176 75 L214 132 L263 151 L304 195 L348 218" /></svg>
            <span className="cab-map-marker cab-map-start"><MapPin size={17} /></span><span className="cab-map-marker cab-map-end"><MapPin size={18} /></span>
            <span className="cab-map-maplabel">ROUTE SKETCH</span><span className="cab-map-compass">N</span>
          </div>
          <div className="cab-route-endpoints">
            <div><span className="cab-endpoint-dot start" /><span><small>PICKUP</small><strong>{lastRoute?.pickup || 'Your starting point'}</strong></span></div>
            <ArrowRight size={15} />
            <div><span className="cab-endpoint-dot end" /><span><small>DESTINATION</small><strong>{lastRoute?.dropoff || 'Where you are headed'}</strong></span></div>
          </div>
          {mapUrl && <a className="cab-map-link" href={mapUrl} target="_blank" rel="noopener noreferrer">Preview route in Google Maps <ExternalLink size={13} /></a>}
          <div className="cab-route-note"><ShieldCheck size={15} /><p>Exact pickup pin, route, driver details and arrival time are confirmed by the provider—not estimated here.</p></div>
        </aside>
      </div>

      <section className="cab-assistant-section">
        <div className="cab-assistant-heading">
          <div className="cab-assistant-avatar">W</div>
          <div><span className="cab-step-label">02 / RIDE INTELLIGENCE</span><h2>Talk to your ride assistant</h2><p>Change a location, add constraints or prepare another ride in plain language.</p></div>
          <span className="cab-assistant-status"><i /> READY</span>
        </div>
        <div className="cab-conversation">
          {messages.length === 0 ? (
            <div className="cab-empty-conversation"><MessageCircle size={22} /><div><strong>Your ride conversation starts here.</strong><p>Try “Book a cab from VIT Bhopal to Bhopal Junction for 2 people” or use the ride form above.</p></div></div>
          ) : messages.map((message) => (
            <div className={'cab-message cab-message-' + message.role} key={message.id}>
              <span className="cab-message-avatar">{message.role === 'user' ? 'Y' : 'W'}</span>
              <div className="cab-message-body">
                <span className="cab-message-author">{message.role === 'user' ? 'You' : 'Warik'}</span>
                <p>{message.content}</p>
                {message.role === 'assistant' && message.structured_data?.type === 'transport_links' && <ProviderOptions data={message.structured_data} />}
              </div>
            </div>
          ))}
          {busy && <div className="cab-typing"><span /><span /><span /> Warik is preparing your ride request</div>}
        </div>
        {error && <p className="cab-inline-error cab-chat-error"><XCircle size={15} /> {error}</p>}
        <form className="cab-assistant-input" onSubmit={submitAssistantMessage}>
          <input value={assistantInput} onChange={(event) => setAssistantInput(event.target.value)} placeholder="Tell Warik what you need to change…" disabled={busy} />
          <button type="submit" disabled={busy || !assistantInput.trim()} aria-label="Send message"><Send size={17} /></button>
        </form>
        <div className="cab-assistant-hints"><span>Try:</span>
          <button type="button" onClick={() => setAssistantInput('Change my pickup to the main gate')}>Change pickup</button>
          <button type="button" onClick={() => setAssistantInput('I need an SUV for 4 passengers')}>Need an SUV</button>
          <button type="button" onClick={() => setAssistantInput('Schedule this ride for tomorrow morning')}>Schedule a ride</button>
        </div>
      </section>

      <section className="cab-how-it-works">
        <div><span className="cab-step-label">03 / YOU STAY IN CONTROL</span><h2>From request to ride.</h2></div>
        <div className="cab-how-step"><span>1</span><div><strong>Tell Warik</strong><small>Share the route and ride preferences.</small></div></div>
        <div className="cab-how-step"><span>2</span><div><strong>Review providers</strong><small>Open Uber or Ola to check live fare and availability.</small></div></div>
        <div className="cab-how-step"><span>3</span><div><strong>Approve in the app</strong><small>Confirm the driver, final price and payment yourself.</small></div></div>
      </section>
    </div>
  );
}
