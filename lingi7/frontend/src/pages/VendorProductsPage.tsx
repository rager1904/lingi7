/**
 * VendorProductsPage — create listings (VendorProductSerializer)
 */

import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FormField } from "../components/forms/FormField";
import { productsApi } from "../api/products";
import { vendorApi, type ProductCondition, type ProductEnrichment, type VendorProduct } from "../api/vendor";
import { useAuthStore } from "../store";
import { extractFieldErrors, extractMessage, formatZMW } from "../utils";
import type { Category } from "../types";

const CONDITIONS: { value: ProductCondition; label: string }[] = [
  { value: "NEW", label: "New" },
  { value: "USED", label: "Used — Good" },
  { value: "REFURBISHED", label: "Refurbished" },
];

const SHIPS_FROM_SUGGESTIONS = [
  "Lusaka",
  "Ndola",
  "Kitwe",
  "Livingstone",
  "China",
  "South Africa",
];

const VendorProductsPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [products, setProducts] = useState<VendorProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [sku, setSku] = useState("");
  const [condition, setCondition] = useState<ProductCondition>("NEW");
  const [price, setPrice] = useState("");
  const [compareAtPrice, setCompareAtPrice] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [shipsFrom, setShipsFrom] = useState("Lusaka");
  const [initialQuantity, setInitialQuantity] = useState("1");
  const [trackInventory, setTrackInventory] = useState(true);
  const [productImage, setProductImage] = useState<File | null>(null);
  const [enrichingId, setEnrichingId] = useState<number | null>(null);
  const [enrichmentById, setEnrichmentById] = useState<Record<number, ProductEnrichment>>({});
  const [expandedEnrichmentId, setExpandedEnrichmentId] = useState<number | null>(null);
  const [applyingId, setApplyingId] = useState<number | null>(null);
  const [storeStatus, setStoreStatus] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      vendorApi.listProducts(),
      productsApi.categories(),
      vendorApi.storeMe().catch(() => null),
    ])
      .then(([prods, cats, store]) => {
        setProducts(prods);
        setCategories(cats);
        setStoreStatus(store?.status ?? null);
        if (cats.length && !categoryId) setCategoryId(String(cats[0].id));
        setError(null);
      })
      .catch(async (err) => {
        const store = await vendorApi.storeMe().catch(() => null);
        setStoreStatus(store?.status ?? null);
        setError(extractMessage(err));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (user?.role !== "VENDOR") {
      navigate("/account", { replace: true });
      return;
    }
    load();
  }, [user, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetForm = () => {
    setName("");
    setDescription("");
    setSku("");
    setCondition("NEW");
    setPrice("");
    setCompareAtPrice("");
    setWeightKg("");
    setShipsFrom("Lusaka");
    setInitialQuantity("1");
    setTrackInventory(true);
    setProductImage(null);
    setFieldErrors({});
  };

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = "Product name is required.";
    if (!description.trim()) errs.description = "Description is required.";
    if (!categoryId) errs.category = "Select a category.";
    if (!price || parseFloat(price) <= 0) errs.price = "Enter a valid price greater than 0.";
    if (compareAtPrice && parseFloat(compareAtPrice) <= parseFloat(price || "0")) {
      errs.compare_at_price = "Compare-at price must be higher than the sale price.";
    }
    if (weightKg && parseFloat(weightKg) <= 0) {
      errs.weight_kg = "Weight must be greater than 0 kg.";
    }
    if (trackInventory && (!initialQuantity || parseInt(initialQuantity, 10) < 0)) {
      errs.initial_quantity = "Enter stock quantity (0 or more).";
    }
    return errs;
  };

  const handleCreate = async () => {
    const errs = validate();
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }

    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      const created = await vendorApi.createProduct({
        name: name.trim(),
        description: description.trim(),
        category: Number(categoryId),
        price,
        sku: sku.trim() || undefined,
        condition,
        compare_at_price: compareAtPrice || null,
        weight_kg: weightKg || null,
        ships_from: shipsFrom.trim(),
        initial_quantity: trackInventory ? parseInt(initialQuantity, 10) || 0 : 0,
        track_inventory: trackInventory,
      });

      if (productImage) {
        await vendorApi.uploadProductImage(created.id, productImage, name.trim());
        vendorApi.enrichProduct(created.id).catch(() => undefined);
      }

      await vendorApi.submitProduct(created.id);
      setShowForm(false);
      resetForm();
      load();
    } catch (err) {
      setFieldErrors(extractFieldErrors(err));
      setError(extractMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const pollEnrichment = async (productId: number, attempts = 12) => {
    for (let i = 0; i < attempts; i += 1) {
      const data = await vendorApi.getEnrichment(productId);
      setEnrichmentById((prev) => ({ ...prev, [productId]: data }));
      if (data.enrichment_status === "COMPLETED" || data.enrichment_status === "FAILED") {
        return data;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    return enrichmentById[productId];
  };

  const handleEnrich = async (productId: number) => {
    setEnrichingId(productId);
    setError(null);
    try {
      await vendorApi.enrichProduct(productId);
      setExpandedEnrichmentId(productId);
      await pollEnrichment(productId);
      load();
    } catch (err) {
      setError(extractMessage(err));
    } finally {
      setEnrichingId(null);
    }
  };

  const handleApplyEnrichment = async (productId: number) => {
    setApplyingId(productId);
    setError(null);
    try {
      await vendorApi.applyEnrichment(productId, [
        "title",
        "description",
        "category",
        "seo",
      ]);
      load();
    } catch (err) {
      setError(extractMessage(err));
    } finally {
      setApplyingId(null);
    }
  };

  const handleToggleEnrichment = async (productId: number) => {
    if (expandedEnrichmentId === productId) {
      setExpandedEnrichmentId(null);
      return;
    }
    setExpandedEnrichmentId(productId);
    if (!enrichmentById[productId]) {
      try {
        const data = await vendorApi.getEnrichment(productId);
        setEnrichmentById((prev) => ({ ...prev, [productId]: data }));
      } catch (err) {
        setError(extractMessage(err));
      }
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-sm text-gray-500">
        Loading products...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-5 sm:px-6 lg:px-8">
      <button onClick={() => navigate("/vendor")} className="text-sm text-gray-500 min-h-0">
        ← Dashboard
      </button>

      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold tracking-[.16em] text-blue-600">CATALOG</p>
          <h1 className="mt-1 text-4xl font-black tracking-tight text-slate-950">My products</h1>
          <p className="text-sm text-gray-500">Create drafts and submit for admin approval.</p>
        </div>
        <button
          onClick={() => {
            setShowForm((v) => !v);
            if (showForm) resetForm();
          }}
          className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-600/20 min-h-0"
        >
          {showForm ? "Cancel" : "+ Add product"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 space-y-1">
          <p>{error}</p>
          {storeStatus === "PENDING" && (
            <p className="text-gray-700">
              Your store is awaiting approval. Product management unlocks once an admin approves
              your store.
            </p>
          )}
          {storeStatus === "REJECTED" && (
            <Link to="/vendor/store" className="inline-block text-emerald-700 font-medium">
              Review store registration →
            </Link>
          )}
        </div>
      )}

      {showForm && (
        <div className="rounded-3xl border border-slate-200 bg-white p-6 space-y-5 shadow-sm">
          <h2 className="font-semibold text-gray-800">New product listing</h2>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-gray-600">Basic info</h3>

            <FormField label="Product name" required error={fieldErrors.name}>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </FormField>

            <FormField label="Description" required error={fieldErrors.description}>
              <textarea
                className="input"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Materials, dimensions, warranty, what's included..."
              />
            </FormField>

            <FormField label="Category" required error={fieldErrors.category}>
              <select
                className="input"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
              >
                {categories.length === 0 && (
                  <option value="">No categories — contact support</option>
                )}
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="SKU" hint="Optional internal product code.">
              <input
                className="input"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder="e.g. FAN-001"
              />
            </FormField>

            <FormField label="Condition" required>
              <select
                className="input"
                value={condition}
                onChange={(e) => setCondition(e.target.value as ProductCondition)}
              >
                {CONDITIONS.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </FormField>
          </section>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-gray-600">Pricing (ZMW)</h3>

            <FormField label="Sale price" required error={fieldErrors.price}>
              <input
                className="input"
                type="number"
                min="0.01"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="0.00"
              />
            </FormField>

            <FormField
              label="Compare-at price"
              error={fieldErrors.compare_at_price}
              hint="Optional. Show a higher 'was' price for promotions."
            >
              <input
                className="input"
                type="number"
                min="0.01"
                step="0.01"
                value={compareAtPrice}
                onChange={(e) => setCompareAtPrice(e.target.value)}
                placeholder="Optional"
              />
            </FormField>
          </section>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-gray-600">Shipping & inventory</h3>

            <FormField label="Ships from" hint="City or country of origin.">
              <input
                className="input"
                list="ships-from-list"
                value={shipsFrom}
                onChange={(e) => setShipsFrom(e.target.value)}
              />
              <datalist id="ships-from-list">
                {SHIPS_FROM_SUGGESTIONS.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </FormField>

            <FormField
              label="Weight (kg)"
              error={fieldErrors.weight_kg}
              hint="Optional. Used for delivery estimates."
            >
              <input
                className="input"
                type="number"
                min="0.001"
                step="0.001"
                value={weightKg}
                onChange={(e) => setWeightKg(e.target.value)}
                placeholder="e.g. 1.5"
              />
            </FormField>

            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={trackInventory}
                onChange={(e) => setTrackInventory(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-emerald-600"
              />
              Track inventory (deduct stock when orders are placed)
            </label>

            {trackInventory && (
              <FormField label="Initial stock quantity" required error={fieldErrors.initial_quantity}>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="1"
                  value={initialQuantity}
                  onChange={(e) => setInitialQuantity(e.target.value)}
                />
              </FormField>
            )}
          </section>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-gray-600">Photos</h3>
            <FormField
              label="Product image"
              hint="Recommended. Upload at least one clear photo before going live."
            >
              <input
                type="file"
                accept="image/*"
                className="block w-full text-sm text-gray-600"
                onChange={(e) => setProductImage(e.target.files?.[0] ?? null)}
              />
              {productImage && (
                <p className="mt-1 text-xs text-emerald-600">Selected: {productImage.name}</p>
              )}
            </FormField>
          </section>

          <button
            onClick={handleCreate}
            disabled={submitting || categories.length === 0}
            className="btn-primary w-full py-3"
          >
            {submitting ? "Saving..." : "Create & Submit for Review"}
          </button>
        </div>
      )}

      {products.length === 0 ? (
        <div className="card p-6 text-center text-sm text-gray-500">
          <p>No listings yet.</p>
          <Link to="/vendor/store" className="mt-2 inline-block text-emerald-600 font-medium">
            Register your store first →
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {products.map((p) => {
            const enrichment = enrichmentById[p.id];
            const isExpanded = expandedEnrichmentId === p.id;
            return (
            <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 truncate">{p.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {formatZMW(p.price)}
                    {p.compare_at_price ? ` · was ${formatZMW(p.compare_at_price)}` : ""}
                    {p.sku ? ` · SKU ${p.sku}` : ""}
                  </p>
                  <p className="text-xs text-gray-400 mt-1 line-clamp-1">{p.description}</p>
                  {p.enrichment_status && p.enrichment_status !== "PENDING" && (
                    <p className="text-xs text-emerald-700 mt-1">
                      AI: {p.enrichment_status.replace("_", " ")}
                      {p.enriched_at
                        ? ` · ${new Date(p.enriched_at).toLocaleDateString()}`
                        : ""}
                    </p>
                  )}
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                    p.status === "APPROVED"
                      ? "bg-green-100 text-green-800"
                      : p.status === "REJECTED"
                        ? "bg-red-100 text-red-800"
                        : "bg-yellow-100 text-yellow-800"
                  }`}
                >
                  {p.status}
                </span>
              </div>
              {p.rejection_reason && (
                <p className="mt-2 text-xs text-red-600">{p.rejection_reason}</p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleEnrich(p.id)}
                  disabled={enrichingId === p.id}
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                >
                  {enrichingId === p.id ? "Enhancing..." : "Enhance with AI"}
                </button>
                {(p.enrichment_status === "COMPLETED" || enrichment) && (
                  <button
                    type="button"
                    onClick={() => handleToggleEnrichment(p.id)}
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {isExpanded ? "Hide suggestions" : "View suggestions"}
                  </button>
                )}
              </div>
              {isExpanded && enrichment && (
                <div className="mt-3 rounded-lg bg-gray-50 p-3 text-xs space-y-2">
                  {enrichment.enrichment_error && (
                    <p className="text-red-600">{enrichment.enrichment_error}</p>
                  )}
                  {enrichment.ai_enhanced_title && (
                    <p>
                      <span className="font-medium text-gray-700">Suggested title:</span>{" "}
                      {enrichment.ai_enhanced_title}
                    </p>
                  )}
                  {enrichment.descriptions_i18n?.en && (
                    <p className="line-clamp-3">
                      <span className="font-medium text-gray-700">Description:</span>{" "}
                      {enrichment.descriptions_i18n.en}
                    </p>
                  )}
                  {enrichment.meta_title && (
                    <p>
                      <span className="font-medium text-gray-700">SEO title:</span>{" "}
                      {enrichment.meta_title}
                    </p>
                  )}
                  {enrichment.suggested_category_name && (
                    <p>
                      <span className="font-medium text-gray-700">Category:</span>{" "}
                      {enrichment.suggested_category_name}
                    </p>
                  )}
                  {enrichment.image_quality_scores?.overall != null && (
                    <p>
                      <span className="font-medium text-gray-700">Image quality:</span>{" "}
                      {Math.round(enrichment.image_quality_scores.overall * 100)}%
                    </p>
                  )}
                  {enrichment.enrichment_status === "COMPLETED" && (
                    <button
                      type="button"
                      onClick={() => handleApplyEnrichment(p.id)}
                      disabled={applyingId === p.id}
                      className="mt-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {applyingId === p.id ? "Applying..." : "Apply suggestions"}
                    </button>
                  )}
                </div>
              )}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default VendorProductsPage;
