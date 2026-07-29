import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import useEmblaCarousel from "embla-carousel-react";
import { Link, useNavigate } from "react-router-dom";
import { productsApi, storesApi } from "../api/resources";
import { useCartStore, useAuthStore, useWishlistStore } from "../store";
import { useForYou, useLikeToggle } from "../hooks";
import { NewsletterForm } from "../components/forms/NewsletterForm";
import RevealOnView from "../components/motion/RevealOnView";
import { formatZMW } from "../utils";
import type { ProductListItem, PublicStore } from "../types";

type DemoProduct = ProductListItem & { rating: number; badge?: string; tone: string };

const seedProducts: DemoProduct[] = [
  { id: 101, slug: "nova-headphones", name: "Nova noise-cancelling headphones", store_name: "Lingi Select", category_name: "Electronics", price_zmw: "2190", primary_image_url: "", in_stock: true, stock_quantity: 9, seller_id: "lingi", rating: 4.9, badge: "New", tone: "from-sky-100 via-blue-50 to-violet-100" },
  { id: 102, slug: "arc-bag", name: "Arc everyday carry backpack", store_name: "Modern Supply", category_name: "Fashion", price_zmw: "980", primary_image_url: "", in_stock: true, stock_quantity: 24, seller_id: "modern", rating: 4.8, tone: "from-orange-100 via-amber-50 to-yellow-100" },
  { id: 103, slug: "sol-watch", name: "Sol stainless steel watch", store_name: "Atelier Nine", category_name: "Accessories", price_zmw: "1760", primary_image_url: "", in_stock: true, stock_quantity: 5, seller_id: "atelier", rating: 4.7, badge: "-20%", tone: "from-slate-200 via-white to-slate-100" },
  { id: 104, slug: "luma-speaker", name: "Luma room-filling speaker", store_name: "Sound District", category_name: "Electronics", price_zmw: "640", primary_image_url: "", in_stock: true, stock_quantity: 15, seller_id: "sound", rating: 4.9, tone: "from-fuchsia-100 via-pink-50 to-violet-100" },
  { id: 105, slug: "aero-sneaker", name: "Aero city runner", store_name: "Motion Lab", category_name: "Sports", price_zmw: "1290", primary_image_url: "", in_stock: true, stock_quantity: 12, seller_id: "motion", rating: 4.6, badge: "Trending", tone: "from-cyan-100 via-sky-50 to-blue-100" },
  { id: 106, slug: "muse-lamp", name: "Muse sculptural table lamp", store_name: "House Form", category_name: "Home", price_zmw: "820", primary_image_url: "", in_stock: true, stock_quantity: 8, seller_id: "house", rating: 4.8, tone: "from-rose-100 via-orange-50 to-amber-100" },
];

const categories = [
  ["⌁", "Electronics", "Latest, for less", "from-blue-500 to-cyan-400"], ["◐", "Fashion", "Your signature look", "from-violet-500 to-fuchsia-400"],
  ["⌂", "Home & living", "Objects for every day", "from-teal-500 to-emerald-400"], ["✦", "Beauty", "A little self-care", "from-orange-400 to-rose-400"],
  ["⟡", "Sports & outdoors", "Move with purpose", "from-cyan-500 to-blue-500"], ["▣", "Gaming", "Play without limits", "from-indigo-500 to-violet-500"],
];

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const addItem = useCartStore((s) => s.addItem);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [query, setQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const reducedMotion = useReducedMotion();
  const { data: productResponse, isLoading } = useQuery({ queryKey: ["home-products"], queryFn: () => productsApi.list({ page: 1 }) });
  const { data: storeResponse } = useQuery({ queryKey: ["home-stores"], queryFn: () => storesApi.list() });
  const products = useMemo<DemoProduct[]>(() => productResponse?.results.length ? productResponse.results.map((p, index) => ({ ...p, rating: 4.5 + (index % 5) / 10, tone: seedProducts[index % seedProducts.length].tone })) : seedProducts, [productResponse]);

  const suggestions = useMemo(() => ["Wireless headphones", "Running shoes", "Smart watches"].filter((item) => item.toLowerCase().includes(query.toLowerCase())), [query]);
  const add = (product: DemoProduct) => addItem({ product_id: product.id, product_name: product.name, price_zmw: product.price_zmw, image_url: product.primary_image_url, max_stock: product.stock_quantity, seller_id: product.seller_id ?? "" }, 1);

  return <div className="overflow-hidden bg-[#f8fafc]">
    <motion.section initial={reducedMotion ? undefined : { opacity: 0, y: 16 }} animate={reducedMotion ? undefined : { opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="hero-shell">
      <div className="hero-orb hero-orb-one" /><div className="hero-orb hero-orb-two" />
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1.05fr_.95fr] lg:px-8 lg:py-24">
        <div className="relative z-10 flex flex-col justify-center">
          <p className="mb-5 text-sm font-semibold tracking-[0.18em] text-cyan-200">MADE FOR DISCOVERY</p>
          <h1 className="max-w-xl text-5xl font-black tracking-[-0.06em] text-white sm:text-6xl lg:text-7xl">Everything worth finding.</h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-blue-100">A smarter, safer marketplace for the things you love — curated from people and stores you can trust.</p>
          <div className="relative mt-8 max-w-xl">
            <div className="flex rounded-2xl bg-white p-1.5 shadow-[0_24px_60px_rgba(3,16,54,.35)]">
              <span className="flex items-center px-3 text-slate-400">⌕</span>
              <input value={query} onFocus={() => setShowSuggestions(true)} onChange={(e) => { setQuery(e.target.value); setShowSuggestions(true); }} onKeyDown={(e) => e.key === "Enter" && navigate(`/?q=${encodeURIComponent(query)}`)} aria-label="Search Lingi7" placeholder="Search products, brands and more" className="min-w-0 flex-1 bg-transparent py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400" />
              <button onClick={() => navigate(`/?q=${encodeURIComponent(query)}`)} className="rounded-xl bg-blue-600 px-5 text-sm font-bold text-white transition hover:bg-blue-500">Explore</button>
            </div>
            {showSuggestions && <div className="absolute z-20 mt-2 w-full rounded-2xl border border-white/50 bg-white p-3 shadow-2xl"><p className="px-3 pb-2 text-xs font-bold uppercase tracking-wider text-slate-400">Popular searches</p>{(suggestions.length ? suggestions : ["Tech essentials", "Home upgrades", "Gifts under K500"]).map((term) => <button key={term} onMouseDown={() => navigate(`/?q=${term}`)} className="block w-full rounded-xl px-3 py-2 text-left text-sm text-slate-700 hover:bg-blue-50">⌕ &nbsp;{term}</button>)}</div>}
          </div>
          <Link to="/shops" className="mt-5 inline-flex w-fit items-center rounded-xl border border-white/30 bg-white/10 px-5 py-3 text-sm font-bold text-white backdrop-blur transition hover:-translate-y-0.5 hover:bg-white/20">Browse stores →</Link>
          <div className="mt-9 flex flex-wrap gap-x-7 gap-y-3 text-sm text-blue-100"><span>◈ Verified sellers</span><span>◈ Secure checkout</span><span>◈ Delivery tracking</span></div>
        </div>
        <div className="hero-products relative min-h-[380px] sm:min-h-[440px]">
          {products.slice(0, 3).map((p, i) => {
            const positions = ["headphone", "shoe", "watch"];
            return <Link key={p.id} to={`/products/${p.slug}`} className={`product-visual ${positions[i]} overflow-hidden`}>
              {p.primary_image_url ? <img src={p.primary_image_url} alt={p.name} className="h-full w-full object-cover" loading={i === 0 ? "eager" : "lazy"} /> : <span className="text-7xl opacity-40">✦</span>}
              <span>{p.name.toUpperCase()}</span>
            </Link>;
          })}
        </div>
      </div>
    </motion.section>

    <main className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 lg:py-20">
      <section aria-labelledby="categories" className="mb-20"><SectionHeading id="categories" title="Start with a feeling" link="Explore categories" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{categories.map(([icon, name, copy, tone]) => <button key={name} onClick={() => navigate(`/?category=${name}`)} className="category-card group text-left"><span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${tone} text-2xl text-white shadow-lg transition group-hover:scale-110`}>{icon}</span><span><b className="block text-base text-slate-900">{name}</b><small className="text-slate-500">{copy}</small></span><span className="ml-auto text-slate-400 transition group-hover:translate-x-1">→</span></button>)}</div>
      </section>

      <section className="deal-surface mb-20 overflow-hidden rounded-[28px] p-6 sm:p-9"><div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-bold tracking-[.18em] text-cyan-300">LIMITED DROP</p><h2 className="mt-1 text-3xl font-black tracking-tight text-white">Flash deals, beautifully timed.</h2></div><div className="flex gap-2 text-white"><Time unit="08" /><Time unit="45" /><Time unit="32" /></div></div><div className="grid gap-4 md:grid-cols-3">{products.slice(0,3).map((p) => <DealCard key={p.id} product={p} add={add} />)}</div></section>

      {/* Personalised "For You" section — shown for logged-in users */}
      {isAuthenticated && <ForYouSection add={add} />}

      <RevealOnView><FeaturedCarousel products={products} add={add} /></RevealOnView>
      <StorefrontRail stores={storeResponse?.results ?? []} />
      <ProductRail title="Trending now" caption="The marketplace is talking about these" products={products} add={add} loading={isLoading} />
      <section className="my-20 grid gap-7 rounded-[32px] bg-gradient-to-br from-violet-700 via-blue-700 to-cyan-600 p-8 text-white lg:grid-cols-[1fr_.8fr] lg:p-12"><div><p className="text-sm font-bold tracking-[.18em] text-cyan-200">LINGI INTELLIGENCE</p><h2 className="mt-3 text-4xl font-black tracking-tight">Shopping that gets smarter with you.</h2><p className="mt-4 max-w-lg text-blue-100">Ask Lingi anything: compare products, discover your style, or find the perfect option within your budget.</p><button className="mt-7 rounded-xl bg-white px-5 py-3 text-sm font-bold text-blue-700 shadow-xl transition hover:-translate-y-0.5" onClick={() => document.getElementById("assistant")?.scrollIntoView({ behavior: "smooth" })}>Meet your shopping assistant →</button></div><div id="assistant" className="glass-chat self-center rounded-3xl p-5 shadow-2xl"><div className="flex items-center gap-3 border-b border-white/15 pb-4"><span className="grid h-10 w-10 place-items-center rounded-full bg-cyan-300 text-blue-950">✦</span><div><b>Ask Lingi</b><p className="text-xs text-blue-100">Your personal shopping guide</p></div></div><div className="my-5 rounded-2xl bg-white/10 p-4 text-sm text-blue-50">I can help find a thoughtful gift, compare choices, or build a look around your budget.</div><button className="w-full rounded-xl bg-white/15 px-4 py-3 text-left text-sm text-blue-100">Try: "Find a gift under K1,000"</button></div></section>
      <ProductRail title="New arrivals" caption="Fresh finds, selected for you" products={[...products].reverse()} add={add} loading={isLoading} />
      <section className="my-20 grid items-center gap-10 border-y border-slate-200 py-14 md:grid-cols-2"><div><p className="text-sm font-bold tracking-[.16em] text-blue-600">THE LINGI7 STANDARD</p><h2 className="mt-3 text-4xl font-black tracking-tight text-slate-950">Made for moments that matter.</h2></div><div className="grid grid-cols-3 gap-5 text-center"><Stat value="1.2M+" label="products to explore" /><Stat value="98%" label="verified sellers" /><Stat value="24/7" label="support when needed" /></div></section>
      <section className="mb-8 rounded-[32px] bg-white p-8 shadow-sm ring-1 ring-slate-200 sm:p-12"><div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center"><div><h2 className="text-3xl font-black tracking-tight text-slate-950">A better kind of inbox.</h2><p className="mt-2 text-slate-500">Weekly drops, member-only offers, and the internet's best finds.</p></div><NewsletterForm /></div></section>
    </main>
  </div>;
};

// ─── For You Section ──────────────────────────────────────────────────────────

const ForYouSection: React.FC<{ add: (p: DemoProduct) => void }> = ({ add }) => {
  const { data: sections, isLoading } = useForYou(10);
  if (isLoading || !sections?.length) return null;

  return (
    <>
      {sections.map((section) => (
        <RevealOnView key={section.strategy}>
          <section className="mb-20">
            <div className="mb-6 flex items-end justify-between">
              <div>
                <p className="text-sm font-bold tracking-[.16em] text-blue-600">
                  {section.strategy === "hybrid" ? "FOR YOU" : section.strategy.toUpperCase().replace("_", " ")}
                </p>
                <h2 className="mt-1 text-3xl font-black tracking-tight text-slate-950">{section.title}</h2>
                <p className="mt-1 text-sm text-slate-500">{section.subtitle}</p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {section.products.slice(0, 6).map((p: any) => (
                <ProductCard key={p.id} product={{ ...p, rating: 4.7, tone: "from-blue-50 via-white to-violet-100" }} add={add} />
              ))}
            </div>
          </section>
        </RevealOnView>
      ))}
    </>
  );
};

// ─── Like Button (with API integration) ──────────────────────────────────────

const LikeButton: React.FC<{ productId: number; className?: string }> = ({ productId, className }) => {
  const { isAuthenticated } = useAuthStore();
  const likeToggle = useLikeToggle();
  const isLiked = useWishlistStore((s) => s.likedProductIds.has(productId));

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isAuthenticated) return;
    likeToggle.mutate(productId);
  };

  return (
    <button
      onClick={handleClick}
      aria-label={isLiked ? "Unlike" : "Like"}
      className={`grid h-8 w-8 place-items-center rounded-full bg-white/90 transition-all ${
        isLiked ? "text-red-500 shadow-md" : "text-slate-700"
      } ${className ?? ""}`}
    >
      {isLiked ? "♥" : "♡"}
    </button>
  );
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const SectionHeading = ({ id, title, link }: {id: string; title: string; link: string}) => <div className="mb-6 flex items-end justify-between"><h2 id={id} className="text-3xl font-black tracking-tight text-slate-950">{title}</h2><button className="text-sm font-bold text-blue-600 hover:text-blue-700">{link} →</button></div>;
const Time = ({ unit }: { unit: string }) => <span className="rounded-xl bg-white/10 px-3 py-2 text-xl font-black backdrop-blur">{unit}</span>;
const Stat = ({ value, label }: {value: string; label: string}) => <div><p className="text-3xl font-black text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{label}</p></div>;
const DealCard = ({product, add}: {product: DemoProduct; add: (p: DemoProduct) => void}) => <div className="rounded-2xl bg-white/[.07] p-4 backdrop-blur"><Link to={`/products/${product.slug}`} className={`grid h-32 place-items-center overflow-hidden rounded-xl bg-gradient-to-br ${product.tone}`}>{product.primary_image_url ? <img src={product.primary_image_url} alt={product.name} className="h-full w-full object-cover" loading="lazy" /> : <span className="text-5xl text-white/60">✦</span>}</Link><div className="mt-3 flex items-start justify-between gap-2"><div><Link to={`/products/${product.slug}`} className="text-sm font-semibold text-white line-clamp-1 hover:underline">{product.name}</Link><p className="mt-1 font-black text-cyan-200">{formatZMW(product.price_zmw)}</p></div><button onClick={() => add(product)} aria-label={`Add ${product.name}`} className="rounded-lg bg-blue-500 px-3 py-2 text-sm font-bold text-white hover:bg-blue-400">+</button></div></div>;
const FeaturedCarousel = ({ products, add }: { products: DemoProduct[]; add: (product: DemoProduct) => void }) => {
  const [emblaRef, emblaApi] = useEmblaCarousel({ align: "start", containScroll: "trimSnaps" });
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);
  const update = useCallback(() => { setCanPrev(emblaApi?.canScrollPrev() ?? false); setCanNext(emblaApi?.canScrollNext() ?? false); }, [emblaApi]);
  useEffect(() => { if (!emblaApi) return; update(); emblaApi.on("select", update).on("reInit", update); return () => { emblaApi.off("select", update).off("reInit", update); }; }, [emblaApi, update]);
  return <section className="mb-20"><div className="mb-6 flex items-end justify-between"><div><p className="text-sm font-bold tracking-[.16em] text-blue-600">CURATED FOR YOU</p><h2 className="mt-1 text-3xl font-black tracking-tight text-slate-950">Featured finds</h2></div><div className="flex gap-2"><button aria-label="Previous featured products" disabled={!canPrev} onClick={() => emblaApi?.scrollPrev()} className="grid h-10 w-10 place-items-center rounded-full border border-slate-200 bg-white text-lg disabled:opacity-40">←</button><button aria-label="Next featured products" disabled={!canNext} onClick={() => emblaApi?.scrollNext()} className="grid h-10 w-10 place-items-center rounded-full border border-slate-200 bg-white text-lg disabled:opacity-40">→</button></div></div><div className="overflow-hidden" ref={emblaRef}><div className="flex gap-4">{products.slice(0, 6).map((product) => <div key={product.id} className="min-w-0 flex-[0_0_82%] sm:flex-[0_0_46%] lg:flex-[0_0_30%]"><ProductCard product={product} add={add} /></div>)}</div></div></section>;
};
const StorefrontRail = ({ stores }: { stores: PublicStore[] }) => stores.length ? <section className="mb-20"><div className="mb-6 flex items-end justify-between"><div><p className="text-sm font-bold tracking-[.16em] text-blue-600">SHOP BY STORE</p><h2 className="mt-1 text-3xl font-black tracking-tight text-slate-950">Pick a store. Make it yours.</h2><p className="mt-1 text-sm text-slate-500">Choose a merchant to browse and search only its live collection.</p></div><Link to="/shops" className="text-sm font-bold text-blue-600">All shops →</Link></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{stores.slice(0, 4).map((store) => <Link key={store.slug} to={`/shops/${store.slug}`} className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg"><div className={`h-20 bg-gradient-to-br ${["from-blue-600 to-cyan-500", "from-violet-600 to-fuchsia-500", "from-emerald-600 to-teal-500", "from-orange-500 to-amber-400"][store.name.length % 4]} p-3`}><span className="grid h-12 w-12 place-items-center overflow-hidden rounded-xl bg-white text-sm font-black text-slate-950">{store.logo ? <img src={store.logo} alt={`${store.name} logo`} className="h-full w-full object-cover" /> : store.name.slice(0, 2).toUpperCase()}</span></div><div className="p-4"><h3 className="font-black text-slate-950">{store.name}</h3><p className="mt-1 line-clamp-1 text-xs text-slate-500">{store.description || "Verified Lingi7 merchant"}</p><p className="mt-3 text-sm font-bold text-blue-600">Browse this store →</p></div></Link>)}</div></section> : null;
const ProductRail = ({ title, caption, products, add, loading }: {title:string; caption:string; products:DemoProduct[]; add:(p:DemoProduct)=>void; loading:boolean}) => <section className="mb-20"><div className="mb-6 flex items-end justify-between"><div><h2 className="text-3xl font-black tracking-tight text-slate-950">{title}</h2><p className="mt-1 text-sm text-slate-500">{caption}</p></div><Link to="/" className="text-sm font-bold text-blue-600">Shop all →</Link></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{(loading ? seedProducts : products).slice(0,6).map((p) => <ProductCard key={p.id} product={p} add={add} />)}</div></section>;
const ProductCard = ({ product, add }: {product:DemoProduct; add:(p:DemoProduct)=>void}) => <article className="product-card group overflow-hidden rounded-2xl bg-white"><Link to={`/products/${product.slug}`} className={`relative grid aspect-[1.08] place-items-center overflow-hidden bg-gradient-to-br ${product.tone}`}><span className="product-glyph transition duration-500 group-hover:scale-110">{product.primary_image_url ? <img src={product.primary_image_url} alt={product.name} className="h-full w-full object-cover" loading="lazy" /> : "✦"}</span>{product.badge && <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-bold text-slate-700">{product.badge}</span>}<LikeButton productId={product.id} className="absolute right-3 top-3" /></Link><div className="p-4"><p className="text-xs font-medium text-slate-400">{product.store_name}</p><Link to={`/products/${product.slug}`}><h3 className="mt-1 line-clamp-1 font-semibold text-slate-900">{product.name}</h3></Link><div className="mt-3 flex items-center justify-between"><div><p className="font-black text-slate-950">{formatZMW(product.price_zmw)}</p><p className="text-xs text-amber-500">★ {product.rating.toFixed(1)}</p></div><button onClick={() => add(product)} className="grid h-9 w-9 place-items-center rounded-xl bg-slate-950 text-lg font-semibold text-white transition hover:bg-blue-600" aria-label={`Add ${product.name} to cart`}>+</button></div></div></article>;

export default HomePage;
