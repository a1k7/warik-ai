import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ArrowLeft, Send, MapPin, Plane, Building2, Car, Calendar, Star,
  Utensils, Bookmark, Map, Plus, Trash2, Menu, X, MessageSquare,
  Check, ExternalLink, Paperclip, Loader2, Mic, Square, RefreshCw
} from 'lucide-react';
import { AIOrb } from './AIOrb';
import { TripResultCard } from './components/TripResultCard';
import { WorkflowCard } from './components/WorkflowCard';
import { clsx } from 'clsx';
import ReactMarkdown from 'react-markdown';
import {
  fetchConversations, createConversation, fetchConversationDetail,
  deleteConversation, sendMessageInConversation, saveFavoriteRestaurant,
  uploadDocument, sendMessageWithDocument, confirmAgentAction, declineAgentAction, commitmentsApi, voiceApi
} from './api';
import { Conversation, Message } from './types';

const ResultCards = ({ data, onSaveCommitment, savingCommitment, onRefreshFlight }: { data: any; onSaveCommitment?: (proposal: any) => void; savingCommitment?: boolean; onRefreshFlight?: (offerId: string) => void }) => {
  if (!data) return null;

  if (data.commitment_proposal) {
    const proposal = data.commitment_proposal;
    return (
      <div className="mt-4 rounded-xl border border-jprimary/40 bg-jprimary/5 p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-jsecondary">Possible commitment detected</p>
        <p className="mt-2 text-sm font-semibold text-white">{proposal.title}</p>
        {(proposal.counterparty || proposal.due_at) && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-jmuted">
            {proposal.counterparty && <span>Person: <strong className="text-white">{proposal.counterparty}</strong></span>}
            {proposal.due_at && <span>Due: <strong className="text-white">{new Date(proposal.due_at).toLocaleString('en-IN', { timeZone: proposal.timezone || 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })}</strong></span>}
          </div>
        )}
        <p className="mt-1 text-xs text-jmuted">Review the extracted details. Nothing has been saved yet.</p>
        {proposal.saved ? (
          <p className="mt-3 text-xs font-semibold text-emerald-400">✓ Added to your Action Ledger</p>
        ) : (
          <button type="button" disabled={savingCommitment} onClick={() => onSaveCommitment?.(proposal)} className="mt-3 rounded-lg bg-jprimary px-4 py-2 text-xs font-bold text-white disabled:opacity-50">
            {savingCommitment ? 'Saving…' : 'Add to Action Ledger'}
          </button>
        )}
      </div>
    );
  }

  if (data.type === 'trip_summary' || data.type === 'advanced_itinerary') {
    return <TripResultCard data={data as any} />;
  }

  if (data.type === 'workflow_status') {
    return <WorkflowCard data={data as any} onRetried={() => window.location.reload()} />;
  }

  if (data.type === 'transport_links') {
    return (
      <div className="bg-jcard border border-jprimary/30 rounded-2xl p-4 flex flex-col gap-3 mt-4 w-full">
        <h4 className="font-bold text-white text-sm flex items-center gap-2">
          <Car size={16} className="text-jprimary" /> Travel from {data.origin} to {data.destination}
        </h4>
        <p className="text-xs text-jmuted">This opens the provider app for you to review availability and fare. No ride has been booked by Warik.</p>
        <div className="flex flex-col gap-2">
          {Object.entries(data.links || {}).map(([key, url]: [string, any]) => (
            <a key={key} href={url} target="_blank" rel="noopener noreferrer" className="flex justify-between items-center bg-jbg hover:bg-jmuted/10 p-3 rounded-lg border border-jmuted/10 transition-colors">
              <span className="text-sm font-bold text-white flex items-center gap-2 capitalize">Continue in {key}</span>
              <ExternalLink size={14} className="text-jsecondary" />
            </a>
          ))}
        </div>
      </div>
    );
  }

  if (data.type === 'food_list') {
    return (
      <div className="flex flex-col gap-3 mt-4 w-full">
        {data.search_context && (
          <div className="bg-jprimary/10 border border-jprimary/30 rounded-lg p-2 text-xs text-jsecondary flex justify-between items-center">
            <div className="flex items-center gap-2"><MapPin size={12} /><span><strong>{data.search_context.location}</strong></span></div>
          </div>
        )}
        {data.items.map((item: any, idx: number) => (
          <div key={idx} className="bg-jcard border border-jprimary/30 rounded-xl flex flex-col shadow-lg w-full overflow-hidden">
            <div className="flex items-center justify-between p-3 border-b border-jmuted/10 bg-jbg/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-jprimary/20 flex items-center justify-center"><Utensils size={18} className="text-jprimary" /></div>
                <div>
                  <h3 className="font-bold text-white text-sm leading-tight">{item.name}</h3>
                  <p className="text-[10px] text-jsecondary">{item.category} {item.distance_km ? `• ${item.distance_km} km` : ''}</p>
                </div>
              </div>
            </div>
            <div className="p-3 flex flex-col gap-2">
              <p className="text-xs text-jmuted flex items-start gap-1"><MapPin size={12} className="mt-0.5 shrink-0" /><span className="break-words line-clamp-2">{item.address}</span></p>
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-jmuted/10">
                <span className="text-[10px] text-jmuted italic">Source: OSM</span>
                <div className="flex gap-2">
                  <a href={item.maps_url} target="_blank" rel="noopener noreferrer" className="text-[10px] font-bold text-jsecondary bg-jprimary/10 hover:bg-jprimary/20 px-3 py-1.5 rounded">Map</a>
                  <a href={item.zomato_url} target="_blank" rel="noopener noreferrer" className="text-[10px] font-bold text-white bg-red-600 hover:bg-red-700 px-3 py-1.5 rounded">Zomato</a>
                  <a href={item.swiggy_url} target="_blank" rel="noopener noreferrer" className="text-[10px] font-bold text-white bg-orange-500 hover:bg-orange-600 px-3 py-1.5 rounded">Swiggy</a>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }


  if (data.type === 'hotel_list') {
    const items = Array.isArray(data.items) ? data.items : [];

    return (
      <div className="flex flex-col gap-4 mt-4 w-full">
        {data.live_inventory === false && (
          <div className="bg-jcard border border-jprimary/30 rounded-xl p-4">
            <div className="flex items-center gap-2 text-jsecondary text-sm font-bold">
              <Building2 size={16} />
              Live hotel inventory unavailable
            </div>
            <p className="text-xs text-jmuted mt-2">
              Current hotel availability and prices need to be checked with the booking provider.
            </p>
          </div>
        )}

        {items.length > 0 ? (
          items.map((item: any, idx: number) => (
            <div
              key={idx}
              className="bg-jcard border border-jprimary/30 rounded-2xl overflow-hidden flex flex-col shadow-lg w-full"
            >
              <div className="p-4 flex flex-col gap-2">
                <h3 className="font-bold text-white text-base">{item.name}</h3>
                {item.address && (
                  <p className="text-xs text-jmuted flex items-start gap-1">
                    <MapPin size={14} />
                    <span>{item.address}</span>
                  </p>
                )}
                <div className="flex justify-between items-center mt-2 pt-3 border-t border-jmuted/10">
                  <span className="text-sm font-bold text-jsecondary">
                    {item.price_per_night || item.price || 'Price unavailable'}
                    <span className="text-xs text-jmuted font-normal"> / night</span>
                  </span>
                  {item.booking_url && (
                    <a
                      href={item.booking_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-bold text-white bg-jprimary hover:bg-jsecondary px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                    >
                      Book Now <ExternalLink size={12} />
                    </a>
                  )}
                </div>
                {item.total_stay && (
                  <p className="text-xs text-jmuted">
                    Total stay: {item.total_stay}
                  </p>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="bg-jcard border border-jmuted/20 rounded-xl p-4">
            <p className="text-sm text-white font-semibold">
              No live hotel results are available.
            </p>
            <p className="text-xs text-jmuted mt-1">
              Use the external search to check current availability and prices.
            </p>
          </div>
        )}

        {data.search_url && (
          <a
            href={data.search_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 rounded-xl bg-jprimary hover:bg-jsecondary text-white font-bold text-sm px-4 py-3 transition-colors"
          >
            Search hotels and prices <ExternalLink size={14} />
          </a>
        )}
      </div>
    );
  }

  if (data.type === 'flight_list') {
    const items = Array.isArray(data.items) ? data.items : [];
    const originAirport =
      data.origin_airport || data.origin_airport_candidates?.[0];
    const destinationAirport =
      data.destination_airport || data.destination_airport_candidates?.[0];

    return (
      <div className="flex flex-col gap-3 mt-4 w-full">
        {(originAirport || destinationAirport) && (
          <div className="bg-jcard border border-jprimary/30 rounded-xl p-3">
            <p className="text-[10px] uppercase tracking-wider text-jmuted mb-2">
              Resolved airports
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-jmuted">Departure</p>
                <p className="text-sm font-bold text-white">
                  {originAirport?.iata || '—'}
                </p>
                <p className="text-xs text-jsecondary">
                  {originAirport?.name || 'Airport unavailable'}
                </p>
              </div>
              <div>
                <p className="text-xs text-jmuted">Destination</p>
                <p className="text-sm font-bold text-white">
                  {destinationAirport?.iata || '—'}
                </p>
                <p className="text-xs text-jsecondary">
                  {destinationAirport?.name || 'Airport unavailable'}
                </p>
              </div>
            </div>
          </div>
        )}

        {data.live_inventory === false && (
          <div className="bg-jcard border border-jprimary/30 rounded-xl p-4">
            <div className="flex items-center gap-2 text-jsecondary text-sm font-bold">
              <Plane size={16} />
              Live flight inventory unavailable
            </div>
            <p className="text-xs text-jmuted mt-2">
              No live schedules or prices have been verified by this search.
            </p>
          </div>
        )}

        {items.length > 0 ? (
          items.map((item: any, idx: number) => (
            <div
              key={idx}
              className="bg-jcard border border-jmuted/20 rounded-xl p-4 flex flex-col gap-2 w-full"
            >
              <div className="flex justify-between items-center">
                <h4 className="font-bold text-white text-sm flex items-center gap-2">
                  <Plane size={16} className="text-jprimary" />
                  {item.segments?.[0]?.airline || 'Flight'}
                </h4>
                <span className="text-xs font-bold text-jsecondary bg-jprimary/10 px-2 py-1 rounded">
                  {item.price || 'Price unavailable'}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                {item.segments?.map((seg: any, i: number) => (
                  <div
                    key={i}
                    className="flex justify-between text-xs text-jmuted mt-1"
                  >
                    <span>{seg.origin} {seg.departure}</span>
                    <span>→</span>
                    <span>{seg.destination} {seg.arrival}</span>
                  </div>
                ))}
              </div>

              <div className="flex justify-between items-center mt-2 pt-2 border-t border-jmuted/10">
                {item.offer_id && onRefreshFlight ? (
                  <button
                    type="button"
                    onClick={() => onRefreshFlight(item.offer_id)}
                    className="text-xs font-bold text-white bg-jprimary hover:bg-jsecondary px-3 py-1.5 rounded flex items-center gap-2"
                  >
                    Refresh live price <RefreshCw size={12} />
                  </button>
                ) : item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-bold text-white bg-jprimary hover:bg-jsecondary px-3 py-1.5 rounded flex items-center gap-2"
                  >
                    View external options <ExternalLink size={12} />
                  </a>
                ) : null}
                {item.expires_at && (
                  <span className="text-[10px] text-jmuted">Offer expiry: {new Date(item.expires_at).toLocaleString('en-IN')}</span>
                )}
                {typeof item.stops === 'number' && (
                  <span className="text-xs text-jmuted">
                    {item.stops === 0 ? 'Non-stop' : `${item.stops} stop(s)`}
                  </span>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="bg-jcard border border-jmuted/20 rounded-xl p-4">
            <p className="text-sm text-white font-semibold">
              No live flight options are available.
            </p>
            <p className="text-xs text-jmuted mt-1">
              Search externally for current routes, schedules and fares.
            </p>
          </div>
        )}

        {data.search_url && (
          <a
            href={data.search_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 rounded-xl bg-jprimary hover:bg-jsecondary text-white font-bold text-sm px-4 py-3 transition-colors"
          >
            Search flights and prices <ExternalLink size={14} />
          </a>
        )}
      </div>
    );
  }

  return null;
};

export const Chat = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [confirmationBusyId, setConfirmationBusyId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Document upload state
  const [activeDoc, setActiveDoc] = useState<{ id: number; filename: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Voice audio is only transcribed here; the user reviews it before it is sent.
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceState, setVoiceState] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [voiceLanguage, setVoiceLanguage] = useState('hi-IN');
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [voiceError, setVoiceError] = useState('');
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const recordingStartedAtRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const discardRecordingRef = useRef(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const hasProcessedInitialMsg = useRef(false);

  useEffect(() => {
    const init = async () => {
      try {
        if (location.state?.openVoice) {
          setVoiceOpen(true);
          window.history.replaceState({}, document.title);
        }
        const data = await fetchConversations();
        setConversations(data);

        if (location.state?.message && !hasProcessedInitialMsg.current) {
          hasProcessedInitialMsg.current = true;
          const newConv = await createConversation();
          setConversations(prev => [newConv, ...prev]);
          setActiveConvId(newConv.id);
          await executeSend(location.state.message, newConv.id);
          window.history.replaceState({}, document.title);
        } else if (data.length > 0 && !activeConvId) {
          setActiveConvId(data[0].id);
        } else if (data.length === 0 && !location.state?.message) {
          const newConv = await createConversation();
          setConversations([newConv]);
          setActiveConvId(newConv.id);
        }
      } catch (e) { console.error("Init failed", e); }
    };
    init();
  }, [location.state]);

  useEffect(() => {
    if (activeConvId) {
      fetchConversationDetail(activeConvId).then(data => {
        const hydrated: Message[] = (data.messages || []).map((message: Message) => {
          const stored = message.structured_data as any;
          const confirmation = stored?.__confirmation;
          if (!confirmation) return message;
          const { __confirmation: _metadata, ...visibleData } = stored;
          return {
            ...message,
            needs_confirmation: Boolean(confirmation.needs_confirmation && !confirmation.status),
            confirmation_token: confirmation.confirmation_token,
            pending_tool: confirmation.pending_tool,
            pending_args: confirmation.pending_args,
            confirmation_status: confirmation.status || (confirmation.needs_confirmation ? 'pending' : undefined),
            structured_data: Object.keys(visibleData).length ? visibleData : undefined,
          };
        });
        setMessages(hydrated);
      }).catch(e => console.error(e));
    }
  }, [activeConvId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isLoading]);

  const executeSend = async (text: string, convId: number) => {
    setIsLoading(true);
    const tempUserMsg: Message = { id: Date.now(), role: 'user', content: text, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, tempUserMsg]);

    try {
      const res = await sendMessageWithDocument(convId, text, activeDoc?.id);
      const newAssistantMsg: Message = {
        id: Date.now() + 1, role: 'assistant', content: res.reply, structured_data: res.structured_data, needs_confirmation: Boolean(res.needs_confirmation), confirmation_token: res.confirmation_token, pending_tool: res.pending_tool, pending_args: res.pending_args, confirmation_status: res.needs_confirmation ? 'pending' : undefined, created_at: new Date().toISOString()
      };
      setMessages(prev => [...prev, newAssistantMsg]);
      const data = await fetchConversations();
      setConversations(data);
    } catch (err) {
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Error connecting to backend.', created_at: new Date().toISOString() }]);
    } finally { setIsLoading(false); }
  };

  const handleRefreshFlight = (offerId: string) => {
    if (!activeConvId || isLoading || !offerId) return;
    void executeSend(
      `Please refresh this exact flight offer and show its current price and expiry: ${offerId}`,
      activeConvId,
    );
  };

  const handleSaveCommitment = async (message: Message, proposal: any) => {
    if (!proposal?.title || !activeConvId) return;
    setConfirmationBusyId(message.id);
    try {
      await commitmentsApi.create({
        title: proposal.title,
        details: proposal.details || undefined,
        counterparty: proposal.counterparty || undefined,
        due_at: proposal.due_at || undefined,
        source: 'conversation',
      });
      setMessages(prev => prev.map(item => item.id === message.id ? {
        ...item,
        structured_data: {
          ...(item.structured_data || {}),
          type: item.structured_data?.type ?? 'commitment_proposal',
          commitment_proposal: { ...proposal, saved: true },
        },
      } : item));
    } catch (error: any) {
      window.alert(error?.response?.data?.detail || 'Could not add this commitment to the Action Ledger.');
    } finally {
      setConfirmationBusyId(null);
    }
  };

  const handleApprove = async (message: Message) => {
    if (!message.confirmation_token || confirmationBusyId !== null) return;
    setConfirmationBusyId(message.id);
    setMessages(prev => prev.map(item => item.id === message.id ? { ...item, confirmation_status: 'processing' } : item));
    try {
      const result = await confirmAgentAction(message.confirmation_token);
      setMessages(prev => prev.map(item => item.id === message.id ? {
        ...item,
        content: result.reply || 'The approved action has completed.',
        structured_data: result.structured_data as Message['structured_data'],
        needs_confirmation: false,
        confirmation_token: undefined,
        confirmation_status: result.tool_calls?.length && result.tool_calls.every(call => call.success) ? 'approved' : 'failed',
      } : item));
    } catch (error: any) {
      const detail = error?.response?.data?.detail || 'Approval could not be completed. You can retry if the action is still pending.';
      setMessages(prev => prev.map(item => item.id === message.id ? { ...item, confirmation_status: 'pending' } : item));
      window.alert(detail);
    } finally {
      setConfirmationBusyId(null);
    }
  };

  const handleDecline = async (message: Message) => {
    if (!message.confirmation_token || confirmationBusyId !== null) return;
    setConfirmationBusyId(message.id);
    setMessages(prev => prev.map(item => item.id === message.id ? { ...item, confirmation_status: 'processing' } : item));
    try {
      await declineAgentAction(message.confirmation_token);
      setMessages(prev => prev.map(item => item.id === message.id ? {
        ...item,
        needs_confirmation: false,
        confirmation_token: undefined,
        confirmation_status: 'declined',
      } : item));
    } catch (error: any) {
      const detail = error?.response?.data?.detail || 'The action could not be declined. Please retry.';
      setMessages(prev => prev.map(item => item.id === message.id ? { ...item, confirmation_status: 'pending' } : item));
      window.alert(detail);
    } finally {
      setConfirmationBusyId(null);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const text = input;
    setInput('');

    let convId = activeConvId;
    if (!convId) {
      try {
        const newConv = await createConversation();
        setConversations(prev => [newConv, ...prev]);
        setActiveConvId(newConv.id);
        convId = newConv.id;
      } catch (err) {
        alert("Failed to create new chat");
        return;
      }
    }
    executeSend(text, convId!);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await uploadDocument(file, activeConvId || undefined);
      setActiveDoc({ id: result.document_id, filename: result.filename });
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant' as const,
        content: `📄 **${result.filename}** uploaded (${result.page_count} pages). Ask me anything about it.`,
        created_at: new Date().toISOString(),
      }]);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to upload document.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };


  const clearRecordingTimer = () => {
    if (recordingTimerRef.current !== null) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
  };

  const releaseMicrophone = () => {
    mediaStreamRef.current?.getTracks().forEach(track => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
  };

  const startVoiceRecording = async () => {
    setVoiceError('');
    setVoiceTranscript('');
    setRecordingSeconds(0);
    discardRecordingRef.current = false;

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setVoiceError('Voice recording is not supported in this browser. Use a current browser over HTTPS.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      mediaStreamRef.current = stream;

      const supportedTypes = [
        'audio/webm;codecs=opus',
        'audio/mp4',
        'audio/ogg;codecs=opus',
        'audio/webm',
      ];
      const mimeType = supportedTypes.find(type => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      recordingStartedAtRef.current = Date.now();

      recorder.ondataavailable = event => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        clearRecordingTimer();
        releaseMicrophone();
        setVoiceState('idle');
        setVoiceError('The recording was interrupted. Please try again.');
      };
      recorder.onstop = async () => {
        clearRecordingTimer();
        const duration = Math.max(1, Math.round((Date.now() - recordingStartedAtRef.current) / 1000));
        const audio = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        audioChunksRef.current = [];
        releaseMicrophone();

        if (discardRecordingRef.current) {
          discardRecordingRef.current = false;
          setVoiceState('idle');
          return;
        }
        if (!audio.size) {
          setVoiceState('idle');
          setVoiceError('No audio was captured. Please try again.');
          return;
        }

        setVoiceState('transcribing');
        try {
          const result = await voiceApi.transcribe(audio, voiceLanguage, duration);
          setVoiceTranscript(result.transcript.trim());
          if (!result.transcript.trim()) setVoiceError('I could not hear any words. Please record again.');
        } catch (error: any) {
          const detail = error?.response?.data?.detail;
          setVoiceError(typeof detail === 'string' ? detail : 'Transcription failed. Check your connection and voice setup, then try again.');
        } finally {
          setVoiceState('idle');
        }
      };

      recorder.start(250);
      setVoiceState('recording');
      recordingTimerRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartedAtRef.current) / 1000);
        setRecordingSeconds(elapsed);
        if (elapsed >= 28 && mediaRecorderRef.current?.state === 'recording') {
          mediaRecorderRef.current.stop();
        }
      }, 500);
    } catch (error: any) {
      releaseMicrophone();
      const denied = error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError';
      setVoiceError(denied
        ? 'Microphone access is blocked. Allow microphone permission in your browser settings and try again.'
        : 'Could not access the microphone. Check that one is connected and try again.');
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
  };

  const closeVoiceMode = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      discardRecordingRef.current = true;
      mediaRecorderRef.current.stop();
    } else {
      clearRecordingTimer();
      releaseMicrophone();
    }
    setVoiceOpen(false);
    setVoiceState('idle');
    setVoiceTranscript('');
    setVoiceError('');
  };

  const useVoiceTranscript = () => {
    setInput(voiceTranscript);
    setVoiceOpen(false);
    setVoiceTranscript('');
    setVoiceError('');
  };

  useEffect(() => () => {
    discardRecordingRef.current = true;
    clearRecordingTimer();
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
    releaseMicrophone();
  }, []);

  return (
    <div className="warik-chat flex h-[100dvh] bg-jbg w-full overflow-hidden relative">
      {/* SIDEBAR */}
      <div className={clsx("fixed inset-y-0 left-0 z-50 w-72 bg-jcard border-r border-jmuted/20 transform transition-transform duration-300 md:relative md:translate-x-0 flex flex-col", sidebarOpen ? "translate-x-0" : "-translate-x-full")}>
        <div className="p-4 flex items-center justify-between border-b border-jmuted/20">
          <h1 className="text-xl font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-jprimary to-jsecondary">WARIK AI</h1>
          <button onClick={() => setSidebarOpen(false)} className="md:hidden text-jmuted hover:text-white"><X size={20} /></button>
        </div>

        <div className="p-4">
          <button onClick={async () => { const newConv = await createConversation(); setConversations(prev => [newConv, ...prev]); setActiveConvId(newConv.id); setMessages([]); setActiveDoc(null); }} className="w-full bg-jprimary hover:bg-jsecondary text-white py-2 rounded-lg flex items-center justify-center gap-2 font-bold transition-colors">
            <Plus size={18} /> New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 space-y-1">
          {conversations.map(c => (
            <div key={c.id} onClick={() => { setActiveConvId(c.id); setActiveDoc(null); }} className={clsx("group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors", activeConvId === c.id ? "bg-jprimary/10 text-white" : "text-jmuted hover:bg-jmuted/10 hover:text-white")}>
              <div className="flex items-center gap-3 overflow-hidden">
                <MessageSquare size={16} className="shrink-0" />
                <span className="text-sm truncate">{c.title}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* MAIN CHAT AREA */}
      <div className="flex-1 flex flex-col h-full relative w-full overflow-hidden">
        <div className="flex items-center gap-4 p-4 border-b border-jprimary/20 bg-jcard/50 backdrop-blur-md shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden text-white"><Menu size={24} /></button>
          <AIOrb state={isLoading ? 'thinking' : 'idle'} size="sm" />
          <div>
            <h2 className="font-bold text-white tracking-widest hidden md:block">WARIK AI</h2>
            <p className="text-[10px] text-jmuted uppercase tracking-widest">{isLoading ? 'Processing' : 'Online'}</p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6 w-full max-w-4xl mx-auto">
          {messages.map((msg) => (
            <div key={msg.id} className={clsx("flex gap-4 w-full", msg.role === 'user' ? "flex-row-reverse" : "")}>
              <div className={clsx("w-8 h-8 shrink-0 rounded-full flex items-center justify-center border text-xs font-bold", msg.role === 'user' ? "bg-jcard border-jmuted text-white" : "bg-jprimary/20 border-jprimary text-jsecondary")}>
                {msg.role === 'user' ? 'U' : 'W'}
              </div>
              <div className={clsx("px-5 py-4 rounded-2xl text-sm border w-full max-w-[85%] break-words", msg.role === 'user' ? "bg-jcard border-jmuted/30 text-white rounded-tr-sm" : "bg-jprimary/10 border-jprimary/30 text-white rounded-tl-sm")}>
                {msg.role === 'user' ? (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                ) : (
                  <div className="w-full">
                    <div className="prose prose-invert prose-sm max-w-none prose-a:text-jsecondary prose-a:underline prose-strong:text-white prose-p:mb-2 prose-p:last:mb-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                    {msg.structured_data && <ResultCards data={msg.structured_data} onSaveCommitment={(proposal) => handleSaveCommitment(msg, proposal)} savingCommitment={confirmationBusyId === msg.id} onRefreshFlight={handleRefreshFlight} />}
                    {msg.needs_confirmation && msg.confirmation_token && msg.confirmation_status !== 'declined' && msg.confirmation_status !== 'approved' && (
                      <div className="mt-4 rounded-xl border border-amber-400/40 bg-amber-400/5 p-4" role="group" aria-label="Action approval">
                        <div className="flex items-start gap-2">
                          <div className="mt-0.5 rounded-full bg-amber-400/15 p-1.5 text-amber-300"><Check size={15} /></div>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-white">Your approval is required</p>
                            <p className="mt-1 text-xs text-jmuted">Proposed action: <span className="font-semibold text-jsecondary">{msg.pending_tool || 'Assistant action'}</span></p>
                            {msg.pending_args && <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/20 p-2 text-[11px] text-jmuted">{JSON.stringify(msg.pending_args, null, 2)}</pre>}
                            <p className="mt-2 text-[11px] text-jmuted">This approval expires after 10 minutes. Nothing is executed until you approve.</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button type="button" disabled={confirmationBusyId !== null || msg.confirmation_status === 'processing'} onClick={() => handleApprove(msg)} className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">{msg.confirmation_status === 'processing' ? 'Processing…' : 'Approve action'}</button>
                              <button type="button" disabled={confirmationBusyId !== null || msg.confirmation_status === 'processing'} onClick={() => handleDecline(msg)} className="rounded-lg border border-jmuted/30 px-4 py-2 text-xs font-semibold text-jmuted hover:bg-jmuted/10 disabled:cursor-not-allowed disabled:opacity-50">Decline</button>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                    {msg.confirmation_status === 'approved' && <p className="mt-3 text-xs font-semibold text-emerald-400">✓ Approved and executed</p>}
                    {msg.confirmation_status === 'declined' && <p className="mt-3 text-xs font-semibold text-jmuted">Action declined. No operation was executed.</p>}
                    {msg.confirmation_status === 'failed' && <p className="mt-3 text-xs font-semibold text-rose-400">Approval accepted, but the action failed. Check the result above before retrying.</p>}
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-4 w-full">
              <div className="w-8 h-8 shrink-0 rounded-full bg-jprimary/20 border border-jprimary flex items-center justify-center text-jsecondary text-xs font-bold">W</div>
              <div className="px-5 py-4 rounded-2xl bg-jprimary/5 border border-jprimary/20 rounded-tl-sm flex gap-2 items-center">
                <span className="w-2 h-2 bg-jprimary rounded-full animate-bounce"></span>
                <span className="w-2 h-2 bg-jprimary rounded-full animate-bounce delay-75"></span>
                <span className="w-2 h-2 bg-jprimary rounded-full animate-bounce delay-150"></span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="p-4 bg-jcard/50 border-t border-jprimary/20 shrink-0">

          {/* ACTIVE DOCUMENT CHIP */}
          {activeDoc && (
            <div className="max-w-4xl mx-auto mb-2 flex items-center gap-2 text-xs">
              <span className="bg-jprimary/20 text-jsecondary px-3 py-1 rounded-full flex items-center gap-2 border border-jprimary/30">
                📄 {activeDoc.filename}
                <button onClick={() => setActiveDoc(null)} className="text-white/70 hover:text-white ml-1">✕</button>
              </span>
            </div>
          )}

          <form onSubmit={handleSend} className="flex gap-2 w-full max-w-4xl mx-auto">
            {/* HIDDEN FILE INPUT */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.csv,.json,.log,.py,.js,.ts"
              className="hidden"
              onChange={handleFileSelect}
            />

            {/* UPLOAD BUTTON */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || isLoading}
              className="w-12 h-12 shrink-0 rounded-xl bg-jcard border border-jmuted/20 text-jmuted hover:text-white hover:border-jprimary transition-colors flex items-center justify-center disabled:opacity-50"
              title="Upload document"
            >
              {uploading ? <Loader2 size={18} className="animate-spin text-jprimary" /> : <Paperclip size={18} />}
            </button>

            <button
              type="button"
              onClick={() => { setVoiceOpen(true); setVoiceError(''); setVoiceTranscript(''); }}
              disabled={isLoading || uploading}
              className="warik-voice-trigger w-12 h-12 shrink-0 rounded-xl border flex items-center justify-center transition-colors disabled:opacity-50"
              title="Talk to Warik"
              aria-label="Open voice mode"
            >
              <Mic size={18} />
            </button>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={activeDoc ? `Ask about ${activeDoc.filename}...` : "Message Warik..."}
              disabled={isLoading}
              className="flex-1 min-w-0 bg-jcard border border-jmuted/20 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-jprimary disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="w-12 h-12 shrink-0 rounded-xl bg-jprimary text-white flex items-center justify-center disabled:opacity-55 hover:bg-jsecondary transition-colors"
            >
              <Send size={18} />
            </button>
          </form>
        </div>
      </div>


      {voiceOpen && (
        <div className="warik-voice-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && voiceState !== 'transcribing') closeVoiceMode(); }}>
          <section className="warik-voice-panel" role="dialog" aria-modal="true" aria-labelledby="warik-voice-title">
            <button type="button" className="warik-voice-close" onClick={closeVoiceMode} aria-label="Close voice mode" disabled={voiceState === 'transcribing'}><X size={18} /></button>
            <p className="warik-voice-kicker">WARIK · VOICE</p>
            <h2 id="warik-voice-title">Say what you need. Stay in control.</h2>
            <p className="warik-voice-subtitle">Speak naturally in your language. Check the words, edit anything unclear, then send.</p>

            <div className="warik-voice-orb">
              <AIOrb state={voiceState === 'recording' ? 'listening' : voiceState === 'transcribing' ? 'thinking' : 'idle'} size="lg" />
            </div>

            <div className="warik-voice-status" aria-live="polite">
              {voiceState === 'recording' ? 'Listening…' : voiceState === 'transcribing' ? 'Understanding your words…' : voiceTranscript ? 'Transcript ready for review' : 'Ready when you are'}
              {voiceState === 'recording' && <span className="warik-voice-time">{String(Math.floor(recordingSeconds / 60)).padStart(2, '0')}:{String(recordingSeconds % 60).padStart(2, '0')}</span>}
            </div>

            <label className="warik-voice-language">
              <span>Speaking language</span>
              <select value={voiceLanguage} onChange={event => setVoiceLanguage(event.target.value)} disabled={voiceState !== 'idle' || Boolean(voiceTranscript)}>
                <option value="hi-IN">Hindi · हिन्दी</option>
                <option value="en-IN">English · India</option>
                <option value="mr-IN">Marathi · मराठी</option>
                <option value="gu-IN">Gujarati · ગુજરાતી</option>
                <option value="bn-IN">Bengali · বাংলা</option>
                <option value="kn-IN">Kannada · ಕನ್ನಡ</option>
                <option value="ml-IN">Malayalam · മലയാളം</option>
                <option value="pa-IN">Punjabi · ਪੰਜਾਬੀ</option>
                <option value="ta-IN">Tamil · தமிழ்</option>
                <option value="te-IN">Telugu · తెలుగు</option>
              </select>
            </label>

            {voiceError && <p className="warik-voice-error" role="alert">{voiceError}</p>}

            {voiceTranscript && (
              <label className="warik-voice-transcript">
                <span>Review and edit your words</span>
                <textarea value={voiceTranscript} onChange={event => setVoiceTranscript(event.target.value)} rows={3} />
              </label>
            )}

            <div className="warik-voice-actions">
              {voiceState === 'recording' ? (
                <button type="button" className="warik-voice-primary is-recording" onClick={stopVoiceRecording}><Square size={15} fill="currentColor" /> Stop recording</button>
              ) : voiceState === 'transcribing' ? (
                <button type="button" className="warik-voice-primary" disabled><Loader2 size={16} className="animate-spin" /> Transcribing</button>
              ) : voiceTranscript ? (
                <button type="button" className="warik-voice-primary" onClick={useVoiceTranscript} disabled={!voiceTranscript.trim()}><Check size={16} /> Use transcript</button>
              ) : (
                <button type="button" className="warik-voice-primary" onClick={startVoiceRecording}><Mic size={17} /> Start speaking</button>
              )}
              {voiceState !== 'transcribing' && <button type="button" className="warik-voice-secondary" onClick={closeVoiceMode}>Cancel</button>}
            </div>
            <p className="warik-voice-privacy">Up to 28 seconds per recording. Audio goes to your configured speech provider for transcription; the assistant receives nothing until you review and send.</p>
          </section>
        </div>
      )}
    </div>
  );
};
