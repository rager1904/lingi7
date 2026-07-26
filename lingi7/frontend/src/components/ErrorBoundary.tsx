import React from "react";

interface ErrorBoundaryState { hasError: boolean; }
export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };
  static getDerivedStateFromError(): ErrorBoundaryState { return { hasError: true }; }
  componentDidCatch(error: Error) { console.error("Lingi7 interface error", error); }
  render() { if (this.state.hasError) return <main className="grid min-h-screen place-items-center bg-slate-50 px-4 text-center"><section className="max-w-md rounded-3xl border border-slate-200 bg-white p-10 shadow-xl"><p className="text-5xl">✦</p><h1 className="mt-5 text-2xl font-black text-slate-950">A small detour.</h1><p className="mt-2 text-sm leading-6 text-slate-500">This part of Lingi7 could not load. Your cart and account details are safe.</p><button onClick={() => window.location.assign("/")} className="mt-6 rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white hover:bg-blue-600">Return home</button></section></main>; return this.props.children; }
}
