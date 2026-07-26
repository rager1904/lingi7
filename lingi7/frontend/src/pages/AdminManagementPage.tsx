import React from "react";
import { Link, useLocation } from "react-router-dom";

const data: Record<string, { title: string; description: string; columns: string[]; rows: string[][] }> = {
  products: { title: "Catalog control", description: "Moderate listings, quality signals, and marketplace visibility.", columns: ["Product", "Seller", "Inventory", "Status"], rows: [["Nova headphones", "Lingi Select", "9 units", "Live"], ["Arc backpack", "Modern Supply", "24 units", "Live"], ["Sol watch", "Atelier Nine", "5 units", "Review"]] },
  orders: { title: "Order operations", description: "Monitor fulfilment and delivery promises.", columns: ["Order", "Customer", "Amount", "Status"], rows: [["#L7-48021", "T. Banda", "K2,190", "Processing"], ["#L7-48018", "M. Phiri", "K980", "Shipped"], ["#L7-48011", "A. Mwila", "K1,760", "Delivered"]] },
  customers: { title: "Customer trust", description: "Review customer health and marketplace safeguards.", columns: ["Customer", "Orders", "Account", "Last active"], rows: [["Thandi Banda", "12", "Verified", "Today"], ["Mwamba Phiri", "4", "Verified", "Yesterday"], ["Ayo Mwila", "7", "Review", "2 days ago"]] },
  categories: { title: "Category architecture", description: "Shape discovery paths and keep collections useful.", columns: ["Category", "Listings", "Growth", "State"], rows: [["Electronics", "18,402", "+12.4%", "Active"], ["Fashion", "15,216", "+8.1%", "Active"], ["Home & living", "9,884", "+6.3%", "Active"]] },
  coupons: { title: "Offers and coupons", description: "Create measurable promotions without compromising margin.", columns: ["Campaign", "Code", "Redemptions", "State"], rows: [["Welcome to Lingi7", "HELLO10", "1,284", "Active"], ["Weekend drop", "WEEKEND15", "862", "Scheduled"], ["Home refresh", "HOME20", "410", "Active"]] },
  reports: { title: "Marketplace reports", description: "An operational readout for revenue, demand, and service quality.", columns: ["Report", "Period", "Owner", "Updated"], rows: [["Revenue performance", "This month", "Finance", "Now"], ["Seller quality", "This week", "Trust", "Today"], ["Inventory risk", "This week", "Operations", "Today"]] },
  settings: { title: "System settings", description: "Govern policies, service levels, and operational defaults.", columns: ["Setting", "Value", "Owner", "State"], rows: [["Seller verification", "Required", "Trust", "Enabled"], ["Delivery SLA", "3-5 days", "Operations", "Enabled"], ["Buyer notifications", "Transactional", "Support", "Enabled"]] },
  users: { title: "Users and permissions", description: "Manage access with least-privilege controls.", columns: ["User", "Role", "Scope", "State"], rows: [["Operations team", "Operator", "Orders", "Active"], ["Trust & safety", "Moderator", "Catalog", "Active"], ["Finance team", "Analyst", "Reports", "Active"]] },
};
const keys = Object.keys(data);

const AdminManagementPage: React.FC = () => {
  const { pathname } = useLocation();
  const key = pathname.split("/").pop() ?? "products";
  const section = data[key] ?? data.products;
  return <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
    <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-xs font-bold tracking-[.18em] text-blue-600">LINGI7 CONTROL CENTER</p><h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">{section.title}</h1><p className="mt-2 max-w-2xl text-slate-500">{section.description}</p></div><Link to="/dashboard" className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm">Overview</Link></div>
    <nav aria-label="Admin sections" className="mb-8 flex gap-2 overflow-x-auto pb-2">{keys.map((item) => <Link key={item} to={`/admin/${item}`} className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold capitalize ${key === item ? "bg-slate-950 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>{item}</Link>)}</nav>
    <section className="overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-slate-200"><div className="flex items-center justify-between border-b border-slate-100 p-6"><div><h2 className="font-bold text-slate-950">Current workspace</h2><p className="mt-1 text-sm text-slate-500">Demo data is isolated from production actions.</p></div><button className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-blue-700">Create new</button></div><div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr>{section.columns.map((column) => <th key={column} className="px-6 py-4 font-bold">{column}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{section.rows.map((row) => <tr key={row[0]} className="hover:bg-slate-50/70">{row.map((value, index) => <td key={`${value}-${index}`} className="px-6 py-5 font-medium text-slate-700">{index === row.length - 1 ? <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">{value}</span> : value}</td>)}</tr>)}</tbody></table></div></section>
  </main>;
};
export default AdminManagementPage;
