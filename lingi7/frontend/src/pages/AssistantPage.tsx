/**
 * AssistantPage — full-page AI shopping assistant chat
 *
 * The floating assistant widget stays available site-wide; this page is the
 * standalone destination used by the Control Center / platform links so
 * /assistant is a real route instead of a dead link.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store";
import { sendAssistantQuery, type AssistantProduct } from "../api/assistant";
import AssistantMessage from "../components/assistant/AssistantMessage";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  products: AssistantProduct[];
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const WELCOME_MESSAGE =
  "Hello! I'm your Lingi shopping assistant. Ask me to find products, compare options, or help with your order. You can also upload a photo of something you like and I'll find similar items.";

const AssistantPage: React.FC = () => {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: generateId(),
          role: "assistant",
          content: WELCOME_MESSAGE,
          products: [],
        },
      ]);
    }
  }, [messages.length]);

  useEffect(() => {
    if (isAuthenticated) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isAuthenticated]);

  const convertToBase64 = useCallback((file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(new Error("Failed to read file"));
      reader.readAsDataURL(file);
    });
  }, []);

  const handleImageUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const file = files[0];
      if (file.size > 5 * 1024 * 1024) {
        alert("Image must be under 5 MB");
        return;
      }

      try {
        const base64 = await convertToBase64(file);
        setImageBase64(base64);
        setImagePreview(base64);
      } catch {
        alert("Failed to load image");
      }
      e.target.value = "";
    },
    [convertToBase64]
  );

  const clearImage = useCallback(() => {
    setImagePreview(null);
    setImageBase64("");
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if ((!text && !imageBase64) || isLoading) return;

    const userContent = text || "What is this product?";
    setMessages((prev) => [...prev, { id: generateId(), role: "user", content: userContent, products: [] }]);
    setInput("");
    setIsLoading(true);

    const payloadImage = imageBase64;
    clearImage();

    try {
      const result = await sendAssistantQuery({
        query: text || "The user has submitted an image.",
        image: payloadImage,
      });
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: "assistant", content: result.response, products: result.products },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: "Sorry, I couldn't process that right now. Please try again in a moment.",
          products: [],
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [input, imageBase64, isLoading, clearImage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  const resetChat = useCallback(() => {
    setMessages([]);
    setInput("");
    clearImage();
  }, [clearImage]);

  return (
    <main className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-3xl flex-col px-4 py-10 sm:px-6">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-bold tracking-[.16em] text-blue-600">AI SHOPPING ASSISTANT</p>
          <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">Ask Lingi</h1>
          <p className="mt-2 max-w-xl text-sm text-slate-500">
            Find products, compare options, or get help with an order — in one
            conversation.
          </p>
        </div>
        <button
          onClick={resetChat}
          className="w-fit rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm hover:text-slate-900"
        >
          Reset conversation
        </button>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        {!isAuthenticated && (
          <div className="rounded-2xl bg-amber-50 m-4 p-3 text-center text-sm text-amber-800">
            <button
              onClick={() => navigate("/login", { state: { from: "/assistant" } })}
              className="font-semibold underline hover:text-amber-900"
            >
              Log in
            </button>{" "}
            to chat with the assistant.
          </div>
        )}

        <div className="h-[46vh] space-y-3 overflow-y-auto p-4 sm:h-[52vh]">
          {messages.map((msg) => (
            <AssistantMessage key={msg.id} role={msg.role} content={msg.content} products={msg.products} />
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1 rounded-2xl rounded-bl-md bg-gray-100 px-4 py-3">
                <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {imagePreview && (
          <div className="border-t border-gray-100 px-4 py-2">
            <div className="relative inline-block">
              <img src={imagePreview} alt="Upload preview" className="h-16 w-16 rounded-lg object-cover" />
              <button
                type="button"
                onClick={clearImage}
                aria-label="Remove image"
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs text-white hover:bg-red-600"
              >
                &times;
              </button>
            </div>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
          className="flex items-center gap-2 border-t border-gray-100 p-3"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleImageUpload}
            className="hidden"
            aria-label="Upload image"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach image"
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </button>

          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isAuthenticated ? "Ask about a product…" : "Log in to chat"}
            disabled={!isAuthenticated || isLoading}
            className="min-w-0 flex-1 rounded-xl bg-gray-100 px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
          />

          <button
            type="submit"
            disabled={isLoading || (!input.trim() && !imageBase64)}
            aria-label="Send message"
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition hover:bg-brand-700 disabled:opacity-40"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
          </button>
        </form>
      </div>
    </main>
  );
};

export default AssistantPage;