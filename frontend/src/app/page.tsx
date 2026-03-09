"use client";

import { useState, useEffect } from "react";
import { Send, User, Bot, Sparkles } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: str;
  agent?: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => `session-${Math.random().toString(36).slice(2, 9)}`);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch("http://localhost:8000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: input, session_id: sessionId }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.content, agent: data.source_agent },
      ]);
    } catch (err) {
      console.error("Failed to send message", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Header */}
      <header className="p-4 border-b bg-white flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white">
            <Sparkles size={18} />
          </div>
          <h1 className="font-bold text-lg tracking-tight">Skilled Agent Stack</h1>
        </div>
        <div className="text-xs text-slate-400 font-mono">ID: {sessionId}</div>
      </header>

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto p-4 space-y-4 max-w-3xl mx-auto w-full">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${
              msg.role === "user" ? "flex-row-reverse" : "flex-row"
            }`}
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                msg.role === "user" ? "bg-indigo-100" : "bg-white border"
              }`}
            >
              {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div
              className={`p-3 rounded-2xl max-w-[80%] shadow-sm ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-tr-none"
                  : "bg-white border text-slate-800 rounded-tl-none"
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              {msg.agent && (
                <div className={`mt-2 text-[10px] uppercase tracking-widest font-bold ${msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'}`}>
                  Expert: {msg.agent}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-3 animate-pulse">
            <div className="w-8 h-8 rounded-full bg-slate-200" />
            <div className="h-10 w-24 bg-slate-200 rounded-2xl" />
          </div>
        )}
      </main>

      {/* Input */}
      <footer className="p-4 bg-white border-t">
        <form onSubmit={sendMessage} className="max-w-3xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything..."
            className="flex-1 p-3 border rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
          />
          <button
            type="submit"
            disabled={isLoading}
            className="p-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Send size={20} />
          </button>
        </form>
      </footer>
    </div>
  );
}
