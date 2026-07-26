/**
 * TopBar — sticky header with logo, search trigger, cart badge
 */

import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCartStore, useAuthStore } from "../../store";

const TopBar: React.FC = () => {
  const navigate = useNavigate();
  const totalItems = useCartStore((s) => s.totalItems());
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <header className="sticky top-0 z-40 border-b border-gray-200 bg-white shadow-sm">
      <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
        <Link
          to="/"
          className="text-xl font-black text-emerald-600 min-h-0"
          aria-label="Lingi7 home"
        >
          Lingi7
        </Link>

        <div className="flex items-center gap-1">
          {/* Search */}
          <button
            onClick={() => navigate("/?search=1")}
            aria-label="Search"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 min-h-0 h-auto w-auto"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"
              />
            </svg>
          </button>

          {/* Cart */}
          <button
            onClick={() => navigate(isAuthenticated ? "/checkout" : "/login")}
            aria-label={`Cart — ${totalItems} item${totalItems !== 1 ? "s" : ""}`}
            className="relative rounded-lg p-2 text-gray-500 hover:bg-gray-100 min-h-0 h-auto w-auto"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-1.5 6h11"
              />
            </svg>
            {totalItems > 0 && (
              <span
                className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-bold text-white"
                aria-hidden
              >
                {totalItems > 9 ? "9+" : totalItems}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};

export default TopBar;
