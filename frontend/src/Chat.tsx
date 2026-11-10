import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ArrowLeft, Send, MapPin, Plane, Building2, Car, Calendar, Star,
  Utensils, Bookmark, Map, Plus, Trash2, Menu, X, MessageSquare,
  Check, ExternalLink, Paperclip, Loader2
} from 'lucide-react';
import { AIOrb } from './AIOrb';
import { TripResultCard } from './components/TripResultCard';
import { WorkflowCard } from './components/WorkflowCard';
import { clsx } from 'clsx';
import ReactMarkdown from 'react-markdown';
import {
  fetchConversations, createConversation, fetchConversationDetail,
  deleteConversation, sendMessageInConversation, saveFavoriteRestaurant,
  uploadDocument, sendMessageWithDocument
} from './api';
import { Conversation, Message } from './types';

const ResultCards = ({ data }: { data: any }) => {
  if (!data) return null;

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
        <div className="flex flex-col gap-2">
          {Object.entries(data.links || {}).map(([key, url]: [string, any]) => (
            <a key={key} href={url} target="_blank" rel="noopener noreferrer" className="flex justify-between items-center bg-jbg hover:bg-jmuted/10 p-3 rounded-lg border border-jmuted/10 transition-colors">
              <span className="text-sm font-bold text-white flex items-center gap-2 capitalize">Book {key}</span>
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
    return (
      <div className="flex flex-col gap-4 mt-4 w-full">
        {data.items.map((item: any, idx: number) => (
          <div key={idx} className="bg-jcard border border-jprimary/30 rounded-2xl overflow-hidden flex flex-col shadow-lg w-full">
            <div className="p-4 flex flex-col gap-2">
              <div className="flex justify-between items-start">
                <h3 className="font-bold text-white text-base">{item.name}</h3>
              </div>
              <p className="text-xs text-jmuted flex items-start gap-1"><MapPin size={14} /><span>{item.address}</span></p>
              <div className="flex justify-between items-center mt-2 pt-3 border-t border-jmuted/10">
                <span className="text-sm font-bold text-jsecondary">{item.price_per_night || item.price} <span className="text-xs text-jmuted font-normal">/ night</span></span>
                <a href={item.booking_url} target="_blank" rel="noopener noreferrer" className="text-xs font-bold text-white bg-jprimary hover:bg-jsecondary px-4 py-2 rounded-lg transition-colors flex items-center gap-2">
                  Book Now <ExternalLink size={12} />
                </a>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (data.type === 'flight_list') {
    return (
      <div className="flex flex-col gap-3 mt-4 w-full">
        {data.items.map((item: any, idx: number) => (
          <div key={idx} className="bg-jcard border border-jmuted/20 rounded-xl p-4 flex flex-col gap-2 w-full">
            <div className="flex justify-between items-center">
              <h4 className="font-bold text-white text-sm flex items-center gap-2"><Plane size={16} className="text-jprimary" /> {item.segments?.[0]?.airline || 'Flight'}</h4>
              <span className="text-xs font-bold text-jsecondary bg-jprimary/10 px-2 py-1 rounded">{item.price}</span>
            </div>
            <div className="flex flex-col gap-2">
              {item.segments?.map((seg: any, i: number) => (
                <div key={i} className="flex justify-between text-xs text-jmuted mt-1">
                  <span>{seg.departure}</span><span>→</span><span>{seg.arrival}</span>
                </div>
              ))}
            </div>
            <div className="flex justify-between items-center mt-2 pt-2 border-t border-jmuted/10">
              <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-xs font-bold text-white bg-jprimary hover:bg-jsecondary px-3 py-1.5 rounded flex items-center gap-2">
                Book Flight <ExternalLink size={12} />
              </a>
            </div>
          </div>
        ))}
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
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Document upload state
  const [activeDoc, setActiveDoc] = useState<{ id: number; filename: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const hasProcessedInitialMsg = useRef(false);

  useEffect(() => {
    const init = async () => {
      try {
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
      fetchConversationDetail(activeConvId).then(data => setMessages(data.messages)).catch(e => console.error(e));
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
        id: Date.now() + 1, role: 'assistant', content: res.reply, structured_data: res.structured_data, created_at: new Date().toISOString()
      };
      setMessages(prev => [...prev, newAssistantMsg]);
      const data = await fetchConversations();
      setConversations(data);
    } catch (err) {
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Error connecting to backend.', created_at: new Date().toISOString() }]);
    } finally { setIsLoading(false); }
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
                    {msg.structured_data && <ResultCards data={msg.structured_data} />}
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
    </div>
  );
};
