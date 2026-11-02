import React, { useState, useRef, useEffect } from 'react';
import { Send, Check, X, Bot, User as UserIcon, Mic, Square } from 'lucide-react';
import { agentService, voiceService } from '../services/api';
import type { ChatMessage } from '../types';
import { clsx } from 'clsx';
import ReactMarkdown from 'react-markdown'; // <-- IMPORTED

export const Chat: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: '1', role: 'assistant', content: 'Hello! I am Warik. How can I help you today? You can type or press the mic to speak.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await agentService.sendMessage(userMsg.content);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.reply,
        agentData: response
      }]);
    } catch (err: any) {
      let errorMsg = err.response?.data?.detail || err.message || "Unknown error";
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Backend Error: ${errorMsg}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async (msgId: string, token: string, isApproved: boolean) => {
    setMessages(prev => prev.map(m => {
      if (m.id === msgId && m.agentData) {
        return { ...m, agentData: { ...m.agentData, needs_confirmation: false } };
      }
      return m;
    }));

    if (!isApproved) {
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'assistant', content: 'Action cancelled.' }]);
      return;
    }

    try {
      const response = await agentService.confirmAction(token);
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'assistant', content: response.reply }]);
    } catch (err: any) {
      let errorMsg = err.response?.data?.detail || err.message || "Unknown error";
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'assistant', content: `Confirmation failed: ${errorMsg}` }]);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      startTimeRef.current = Date.now();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const durationSeconds = Math.round((Date.now() - startTimeRef.current) / 1000);
        
        const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: '🎤 (Voice message)' };
        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
          const response = await voiceService.sendVoiceMessage(audioBlob, durationSeconds);
          setMessages(prev => prev.map(m => 
            m.id === userMsg.id ? { ...m, content: `🎤 "${response.transcript}"` } : m
          ));
          setMessages(prev => [...prev, {
            id: (Date.now() + 1).toString(),
            role: 'assistant',
            content: response.reply,
            agentData: response
          }]);
        } catch (err: any) {
          let errorMsg = err.response?.data?.detail || err.message || "Voice failed";
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: `Voice Error: ${errorMsg}`
          }]);
        } finally {
          setIsLoading(false);
        }
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      alert("Please allow microphone access in your browser to use voice.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-6rem)] bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="bg-white border-b border-gray-100 p-4 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-burgundy flex items-center justify-center text-white">
          <Bot size={20} />
        </div>
        <div>
          <h2 className="font-semibold text-charcoal">Warik AI</h2>
          <p className="text-xs text-green-600 font-medium">Online</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={clsx("flex gap-4 max-w-[85%]", msg.role === 'user' ? "ml-auto flex-row-reverse" : "")}>
            <div className={clsx(
              "w-8 h-8 rounded-full flex flex-shrink-0 items-center justify-center",
              msg.role === 'user' ? "bg-charcoal text-white" : "bg-burgundy text-white"
            )}>
              {msg.role === 'user' ? <UserIcon size={16} /> : <Bot size={16} />}
            </div>
            
            <div className="space-y-2">
              <div className={clsx(
                "px-4 py-3 rounded-2xl text-sm leading-relaxed overflow-hidden",
                msg.role === 'user' 
                  ? "bg-ivory text-charcoal rounded-tr-sm" 
                  : "bg-burgundy text-white rounded-tl-sm"
              )}>
                {/* RENDER MARKDOWN HERE */}
                <div className={clsx(
                  "prose prose-sm max-w-none prose-a:text-rose prose-a:underline hover:prose-a:text-white prose-strong:text-rose",
                  msg.role === 'user' ? "prose-p:text-charcoal prose-strong:text-charcoal" : "prose-invert"
                )}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              </div>

              {msg.agentData?.needs_confirmation && (
                <div className="bg-white border border-rose rounded-xl p-4 shadow-sm mt-2">
                  <p className="text-sm font-medium text-charcoal mb-3">Action requires approval</p>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => handleConfirm(msg.id, msg.agentData!.confirmation_token!, true)}
                      className="flex-1 bg-burgundy text-white py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 hover:bg-wine transition-colors"
                    >
                      <Check size={16} /> Approve
                    </button>
                    <button 
                      onClick={() => handleConfirm(msg.id, msg.agentData!.confirmation_token!, false)}
                      className="flex-1 bg-ivory text-charcoal py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 hover:bg-gray-200 transition-colors"
                    >
                      <X size={16} /> Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-4">
            <div className="w-8 h-8 rounded-full bg-burgundy flex items-center justify-center text-white">
              <Bot size={16} />
            </div>
            <div className="px-4 py-3 rounded-2xl bg-gray-100 rounded-tl-sm flex gap-1 items-center">
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-75"></span>
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-150"></span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 bg-white border-t border-gray-100">
        <form onSubmit={handleSend} className="flex gap-2">
          <button
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            className={clsx(
              "w-12 h-12 rounded-xl flex items-center justify-center transition-colors",
              isRecording ? "bg-red-500 text-white animate-pulse" : "bg-ivory text-charcoal hover:bg-gray-200"
            )}
          >
            {isRecording ? <Square size={18} /> : <Mic size={18} />}
          </button>
          
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isRecording ? "Listening..." : "Message Warik..."}
            disabled={isRecording}
            className="flex-1 bg-ivory border-none rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-burgundy/50"
          />
          
          <button
            type="submit"
            disabled={!input.trim() || isLoading || isRecording}
            className="bg-burgundy text-white w-12 h-12 rounded-xl flex items-center justify-center disabled:opacity-50 hover:bg-wine transition-colors"
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};