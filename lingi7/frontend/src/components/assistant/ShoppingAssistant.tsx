import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store";
import { sendAssistantQuery, type AssistantProduct } from "../../api/assistant";
import AssistantMessage from "./AssistantMessage";

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

const ShoppingAssistant: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  // Initialize welcome message
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([
        {
          id: generateId(),
          role: "assistant",
          content: WELCOME_MESSAGE,
          products: [],
        },
      ]);
    }
  }, [open, messages.length]);

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

      // Reset the input so the same file can be re-selected
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
    if (!text && !imageBase64) return;
    if (isLoading) return;

    const userContent = text || "What is this product?";
    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: userContent,
      products: [],
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // Clear image after capturing for the request
    const payloadImage = imageBase64;
    clearImage();

    try {
      const result = await sendAssistantQuery({
        query: text || "The user has submitted an image.",
        image: payloadImage,
      });

      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: result.response,
        products: result.products,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content:
          "Sorry, I couldn't process that right now. Please try again in a moment.",
        products: [],
      };
      setMessages((prev) => [...prev, errorMsg]);
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
    <div className="fixed bottom-20 right-4 z-40 sm:bottom-6 sm:right-6">
      {/* Chat Panel */}
      {open && (
        <section className="mb-3 flex w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-2xl">
          {/* Header */}
          <header className="flex items-center justify-between bg-gray-950 px-5 py-4 text-white">
            <div>
              <p className="font-black">Ask Lingi</p>
              <p className="text-xs text-gray-400">Your shopping assistant</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
              className="text-xl leading-none text-gray-400 hover:text-white"
            >
              &times;
            </button>
          </header>

          {/* Messages */}
          <div className="h-72 space-y-3 overflow-y-auto p-4">
            {!isAuthenticated && (
              <div className="rounded-2xl bg-amber-50 p-3 text-center text-sm text-amber-800">
               {" "}
                <button
                  onClick={() => {
                    setOpen(false);
                    navigate("/login");
                  }}
                  className="font-semibold underline hover:text-amber-900"
                >
                  Log in
                </button>{" "}
                to chat with the assistant.
              </div>
            )}

            {messages.map((msg) => (
              <AssistantMessage
                key={msg.id}
                role={msg.role}
                content={msg.content}
                products={msg.products}
              />
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

          {/* Image preview */}
          {imagePreview && (
            <div className="border-t border-gray-100 px-4 py-2">
              <div className="relative inline-block">
                <img
                  src={imagePreview}
                  alt="Upload preview"
                  className="h-16 w-16 rounded-lg object-cover"
                />
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

          {/* Input */}
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
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
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
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
              </svg>
            </button>
          </form>

          {/* Footer */}
          <div className="flex items-center justify-center border-t border-gray-100 bg-gray-50 px-4 py-2">
            <button
              onClick={resetChat}
              className="text-xs text-gray-400 transition hover:text-gray-600"
            >
              Reset conversation
            </button>
          </div>
        </section>
      )}

      {/* Floating toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className="grid h-14 w-14 place-items-center rounded-full bg-brand-600 text-xl text-white shadow-lg shadow-brand-600/30 transition hover:scale-105"
        aria-label="Open AI shopping assistant"
      >
        {open ? (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        )}
      </button>
    </div>
  );
};

export default ShoppingAssistant;
