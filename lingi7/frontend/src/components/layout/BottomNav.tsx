/**
 * BottomNav — fixed mobile bottom navigation with safe-area support
 */

import React from "react";
import { NavLink } from "react-router-dom";
import { useCartStore } from "../../store";

interface NavItem {
  path: string;
  label: string;
  end?: boolean;
  icon: (active: boolean) => React.ReactNode;
  badge?: () => number;
}

const ShopIcon = (active: boolean) => (
  <svg className="h-6 w-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.8} aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.5 1.5 0 012.092 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
  </svg>
);

const OrdersIcon = (active: boolean) => (
  <svg className="h-6 w-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.8} aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
  </svg>
);

const CartIcon = (active: boolean) => (
  <svg className="h-6 w-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.8} aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
  </svg>
);

const AccountIcon = (active: boolean) => (
  <svg className="h-6 w-6" fill={active ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 1.8} aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
  </svg>
);

const BottomNav: React.FC = () => {
  const cartCount = useCartStore((s) => s.totalItems());

  const items: NavItem[] = [
    { path: "/",        label: "Shop",    end: true, icon: ShopIcon },
    { path: "/orders",  label: "Orders",             icon: OrdersIcon },
    { path: "/cart",    label: "Cart",               icon: CartIcon, badge: () => cartCount },
    { path: "/account", label: "Account",             icon: AccountIcon },
  ];

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-gray-200 bg-white pb-safe shadow-[0_-8px_24px_rgba(15,23,42,0.08)] sm:hidden"
      aria-label="Main navigation"
    >
      <div className="mx-auto flex max-w-2xl justify-around">
        {items.map(({ path, label, end, icon, badge }) => (
          <NavLink
            key={path}
            to={path}
            end={end}
            className={({ isActive }) =>
              `relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors ${
                isActive ? "text-emerald-600" : "text-gray-400"
              }`
            }
            aria-label={label}
          >
            {({ isActive }) => (
              <>
                <span className="relative">
                  {icon(isActive)}
                  {badge && badge() > 0 && (
                    <span
                      className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-600 text-[9px] font-bold text-white"
                      aria-hidden
                    >
                      {badge() > 9 ? "9+" : badge()}
                    </span>
                  )}
                </span>
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;
