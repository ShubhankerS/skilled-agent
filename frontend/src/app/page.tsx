"use client";

import { useState, useRef } from "react";
import { Send, User, Bot, Sparkles, Paperclip, Loader2, Image as ImageIcon, X } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  image?: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [sessionId] = useState(() => `session-${Math.random().toString(36).slice(2, 9)}`);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => setSelectedImage(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      await fetch("http://localhost:8000/api/v1/upload", { method: "POST", body: formData });
      alert("Document indexed successfully!");
    } catch (err) { console.error(err); } finally { setIsUploading(false); }
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: "user", content: input, image: selectedImage || undefined };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const currentImage = selectedImage;
    setSelectedImage(null);
    setIsLoading(true);

    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch("http://localhost:8000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          query: input, 
          session_id: sessionId, 
          image_b64: currentImage?.split(",")[1] 
        }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let fullText = "";
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          fullText += decoder.decode(value);
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1].content = fullText;
            return newMessages;
          });
        }
      }
    } catch (err) { console.error(err); } finally { setIsLoading(false); }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900 font-sans">
      <header className="p-4 border-b bg-white flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white"><Sparkles size={18} /></div>
          <h1 className="font-bold text-lg tracking-tight">Skilled Agent Stack</h1>
        </div>
        <div className="text-xs text-slate-400 font-mono">ID: {sessionId}</div>
      </header>

      <main className="flex-1 overflow-y-auto p-4 space-y-4 max-w-3xl mx-auto w-full">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "user" ? "bg-indigo-100" : "bg-white border"}`}>
              {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className={`p-3 rounded-2xl max-w-[80%] shadow-sm ${msg.role === "user" ? "bg-indigo-600 text-white rounded-tr-none" : "bg-white border text-slate-800 rounded-tl-none"}`}>
              {msg.image && <img src={msg.image} className="mb-2 rounded-lg max-h-48" alt="User upload" />}
              <p className="text-sm whitespace-pre-wrap">{msg.content || "..."}</p>
            </div>
          </div>
        ))}
      </main>

      <footer className="p-4 bg-white border-t">
        <div className="max-w-3xl mx-auto">
          {selectedImage && (
            <div className="relative inline-block mb-4">
              <img src={selectedImage} className="h-20 w-20 object-cover rounded-xl border-2 border-indigo-500" alt="Preview" />
              <button onClick={() => setSelectedImage(null)} className="absolute -top-2 -right-2 bg-white rounded-full p-1 shadow-md border text-slate-400 hover:text-red-500"><X size={14} /></button>
            </div>
          )}
          <form onSubmit={sendMessage} className="flex gap-2">
            <button type="button" onClick={() => fileInputRef.current?.click()} className="p-3 text-slate-400 hover:text-indigo-600 hover:bg-slate-50 rounded-xl transition-all"><Paperclip size={20} /></button>
            <button type="button" onClick={() => imageInputRef.current?.click()} className="p-3 text-slate-400 hover:text-indigo-600 hover:bg-slate-50 rounded-xl transition-all"><ImageIcon size={20} /></button>
            
            <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept=".pdf,.txt" />
            <input type="file" ref={imageInputRef} onChange={handleImageUpload} className="hidden" accept="image/*" />
            
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message or upload content..."
              className="flex-1 p-3 border rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
            />
            <button type="submit" disabled={isLoading} className="p-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors"><Send size={20} /></button>
          </form>
        </div>
      </footer>
    </div>
  );
}
