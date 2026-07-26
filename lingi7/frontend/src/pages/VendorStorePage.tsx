/**
 * VendorStorePage — full store registration (StoreRegistrationSerializer)
 */

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FormField } from "../components/forms/FormField";
import { PhoneInput } from "../components/forms/PhoneInput";
import { vendorApi, type VendorStore } from "../api/vendor";
import { useAuthStore } from "../store";
import {
  extractFieldErrors,
  extractMessage,
  formatDate,
  isValidZambianPhone,
  normalizeZambianPhone,
} from "../utils";

const VendorStorePage: React.FC = () => {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [store, setStore] = useState<VendorStore | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [businessType, setBusinessType] = useState<"INDIVIDUAL" | "REGISTERED">("INDIVIDUAL");
  const [tpin, setTpin] = useState("");
  const [nrcOrReg, setNrcOrReg] = useState("");
  const [businessAddress, setBusinessAddress] = useState("");
  const [phoneNumber, setPhoneNumber] = useState(
    user?.phone_number ? normalizeZambianPhone(user.phone_number) : "+260"
  );
  const [payoutAccount, setPayoutAccount] = useState("+260");
  const [payoutProvider, setPayoutProvider] = useState<"MTN" | "AIRTEL">("MTN");
  const [idDocument, setIdDocument] = useState<File | null>(null);
  const [brandName, setBrandName] = useState("");
  const [brandDescription, setBrandDescription] = useState("");
  const [logo, setLogo] = useState<File | null>(null);
  const [banner, setBanner] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [bannerPreview, setBannerPreview] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user?.role !== "VENDOR") {
      navigate("/account", { replace: true });
      return;
    }
    vendorApi
      .storeMe()
      .then((currentStore) => { setStore(currentStore); setBrandName(currentStore.name); setBrandDescription(currentStore.description ?? ""); })
      .catch(() => setStore(null))
      .finally(() => setLoading(false));
  }, [user, navigate]);

  useEffect(() => { if (!logo) { setLogoPreview(null); return; } const url = URL.createObjectURL(logo); setLogoPreview(url); return () => URL.revokeObjectURL(url); }, [logo]);
  useEffect(() => { if (!banner) { setBannerPreview(null); return; } const url = URL.createObjectURL(banner); setBannerPreview(url); return () => URL.revokeObjectURL(url); }, [banner]);

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = "Store name is required.";
    if (!nrcOrReg.trim()) errs.nrc_or_reg_no = "NRC or PACRA registration number is required.";
    if (!businessAddress.trim()) errs.business_address = "Business address is required.";
    if (!isValidZambianPhone(phoneNumber)) {
      errs.phone_number = "Enter a valid MTN, Airtel, or Zamtel mobile number.";
    }
    if (!isValidZambianPhone(payoutAccount)) {
      errs.payout_account = "Enter a valid payout mobile number.";
    }
    if (businessType === "REGISTERED" && !tpin.trim()) {
      errs.tpin = "TPIN is required for registered businesses.";
    }
    if (!idDocument) errs.id_document = "Upload your NRC or PACRA certificate.";
    return errs;
  };

  const handleRegister = async () => {
    const errs = validate();
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }

    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      const created = await vendorApi.registerStore({
        name: name.trim(),
        description: description.trim(),
        business_type: businessType,
        tpin: tpin.trim() || undefined,
        nrc_or_reg_no: nrcOrReg.trim(),
        business_address: businessAddress.trim(),
        phone_number: normalizeZambianPhone(phoneNumber),
        payout_account: normalizeZambianPhone(payoutAccount),
        payout_provider: payoutProvider,
        id_document: idDocument!,
      });
      setStore(created);
      navigate("/vendor");
    } catch (err) {
      setFieldErrors(extractFieldErrors(err));
      setError(extractMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleBrandUpdate = async () => {
    if (!store) return;
    setSubmitting(true); setError(null); setFieldErrors({});
    try {
      const updated = await vendorApi.updateStore({ name: brandName.trim(), description: brandDescription.trim(), logo, banner });
      setStore(updated); setLogo(null); setBanner(null);
    } catch (err) {
      setFieldErrors(extractFieldErrors(err)); setError(extractMessage(err));
    } finally { setSubmitting(false); }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center text-sm text-gray-500">
        Loading...
      </div>
    );
  }

  if (store) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 space-y-4 sm:px-6">
        <p className="text-sm font-bold tracking-[.16em] text-blue-600">SELLER WORKSPACE</p>
        <h1 className="text-4xl font-black tracking-tight text-slate-950">Your store.</h1>
        <div className="card p-4 space-y-3 text-sm">
          <div className="flex justify-between gap-2">
            <span className="text-gray-500">Name</span>
            <span className="font-medium text-gray-900 text-right">{store.name}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-gray-500">Slug</span>
            <span className="font-mono text-xs text-gray-700">{store.slug}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-gray-500">Status</span>
            <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
              {store.status}
            </span>
          </div>
          {store.business_type && (
            <div className="flex justify-between gap-2">
              <span className="text-gray-500">Business type</span>
              <span className="text-gray-900">{store.business_type}</span>
            </div>
          )}
          {store.description && (
            <p className="text-gray-600 border-t border-gray-100 pt-2">{store.description}</p>
          )}
          {store.payout_account && (
            <div className="flex justify-between gap-2 border-t border-gray-100 pt-2">
              <span className="text-gray-500">Payout</span>
              <span className="text-gray-900">
                {store.payout_provider} · {store.payout_account}
              </span>
            </div>
          )}
          {store.rejection_reason && (
            <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700">
              Rejection reason: {store.rejection_reason}
            </p>
          )}
          {store.created_at && (
            <p className="text-xs text-gray-400">Registered {formatDate(store.created_at)}</p>
          )}
        </div>
        <section className="card space-y-4 p-5">
          <div><p className="text-xs font-bold tracking-[.16em] text-blue-600">STOREFRONT DESIGNER</p><h2 className="mt-1 text-xl font-black text-slate-950">Make your tenant store recognisable.</h2><p className="mt-1 text-sm text-slate-500">Your branding appears on your public Lingi7 storefront once the store is approved.</p></div>
          <div className="grid gap-4 sm:grid-cols-2"><div className="rounded-2xl bg-slate-100 p-4"><p className="mb-2 text-xs font-bold text-slate-500">LOGO</p><div className="grid h-20 w-20 place-items-center overflow-hidden rounded-2xl bg-white text-xl font-black text-slate-700 shadow-sm">{logoPreview ? <img src={logoPreview} alt="Logo preview" className="h-full w-full object-cover" /> : store.logo ? <img src={store.logo} alt="Store logo" className="h-full w-full object-cover" /> : store.name.slice(0, 2).toUpperCase()}</div></div><div className="rounded-2xl bg-slate-100 p-4"><p className="mb-2 text-xs font-bold text-slate-500">BANNER</p><div className="h-20 overflow-hidden rounded-xl bg-gradient-to-br from-blue-600 to-violet-600">{bannerPreview ? <img src={bannerPreview} alt="Banner preview" className="h-full w-full object-cover" /> : store.banner && <img src={store.banner} alt="Store banner" className="h-full w-full object-cover" />}</div></div></div>
          <FormField label="Storefront name" required error={fieldErrors.name}><input className="input" value={brandName} onChange={(event) => setBrandName(event.target.value)} /></FormField>
          <FormField label="Storefront description" error={fieldErrors.description}><textarea className="input" rows={3} value={brandDescription} onChange={(event) => setBrandDescription(event.target.value)} placeholder="Tell buyers what makes your store special." /></FormField>
          <div className="grid gap-4 sm:grid-cols-2"><FormField label="Logo" hint="Square JPG, PNG, or WebP."><input type="file" accept="image/png,image/jpeg,image/webp" className="block w-full text-sm" onChange={(event) => setLogo(event.target.files?.[0] ?? null)} /></FormField><FormField label="Banner" hint="Wide JPG, PNG, or WebP."><input type="file" accept="image/png,image/jpeg,image/webp" className="block w-full text-sm" onChange={(event) => setBanner(event.target.files?.[0] ?? null)} /></FormField></div>
          {(error || Object.keys(fieldErrors).length > 0) && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error ?? "Please fix the highlighted fields."}</p>}
          <button disabled={submitting || !brandName.trim()} onClick={handleBrandUpdate} className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">{submitting ? "Saving storefront…" : "Save storefront"}</button>
        </section>
        <button onClick={() => navigate("/vendor")} className="btn-primary w-full py-3">
          Go to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-5 sm:px-6">
      <button onClick={() => navigate("/account")} className="text-sm text-gray-500 min-h-0">
        ← Back
      </button>
      <div>
        <p className="text-sm font-bold tracking-[.16em] text-blue-600">SELLER ONBOARDING</p>
        <h1 className="text-4xl font-black tracking-tight text-slate-950">Start your store.</h1>
        <p className="mt-1 text-sm text-gray-500">
          All fields are required unless marked optional. Your store is reviewed before you can list products.
        </p>
      </div>

      {(error || Object.keys(fieldErrors).length > 0) && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error ?? "Please fix the highlighted fields."}
        </div>
      )}

      <section className="card p-4 space-y-4">
        <h2 className="font-semibold text-gray-800">Store profile</h2>

        <FormField label="Store name" required error={fieldErrors.name}>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Lusaka Electronics"
          />
        </FormField>

        <FormField
          label="Description"
          hint="Tell buyers what you sell and your service area."
        >
          <textarea
            className="input"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief store description"
          />
        </FormField>

        <FormField label="Business type" required>
          <select
            className="input"
            value={businessType}
            onChange={(e) => setBusinessType(e.target.value as "INDIVIDUAL" | "REGISTERED")}
          >
            <option value="INDIVIDUAL">Individual trader</option>
            <option value="REGISTERED">Registered business (PACRA)</option>
          </select>
        </FormField>
      </section>

      <section className="card p-4 space-y-4">
        <h2 className="font-semibold text-gray-800">KYC & compliance</h2>

        <FormField
          label="NRC or PACRA registration number"
          required
          error={fieldErrors.nrc_or_reg_no}
          hint="National ID for individuals, PACRA number for companies."
        >
          <input
            className="input"
            value={nrcOrReg}
            onChange={(e) => setNrcOrReg(e.target.value)}
            placeholder="123456/10/1 or PACRA reg. no."
          />
        </FormField>

        <FormField
          label="TPIN (ZRA Tax PIN)"
          required={businessType === "REGISTERED"}
          error={fieldErrors.tpin}
          hint={businessType === "INDIVIDUAL" ? "Optional for individual traders." : undefined}
        >
          <input
            className="input"
            value={tpin}
            onChange={(e) => setTpin(e.target.value)}
            placeholder="Taxpayer identification number"
          />
        </FormField>

        <FormField label="Business address" required error={fieldErrors.business_address}>
          <textarea
            className="input"
            rows={2}
            value={businessAddress}
            onChange={(e) => setBusinessAddress(e.target.value)}
            placeholder="Plot number, street, city"
          />
        </FormField>

        <FormField
          label="Store contact phone"
          required
          error={fieldErrors.phone_number}
          hint="Zambian mobile number for buyer and admin contact."
        >
          <PhoneInput value={phoneNumber} onChange={setPhoneNumber} />
        </FormField>

        <FormField label="ID document (NRC / PACRA certificate)" required error={fieldErrors.id_document}>
          <input
            type="file"
            accept="image/*,.pdf"
            className="block w-full text-sm text-gray-600"
            onChange={(e) => setIdDocument(e.target.files?.[0] ?? null)}
          />
          {idDocument && (
            <p className="mt-1 text-xs text-emerald-600">Selected: {idDocument.name}</p>
          )}
        </FormField>
      </section>

      <section className="card p-4 space-y-4">
        <h2 className="font-semibold text-gray-800">Payout details</h2>
        <p className="text-xs text-gray-500">
          Escrow releases are sent to this mobile money account after delivery is confirmed.
        </p>

        <FormField label="Payout provider" required>
          <select
            className="input"
            value={payoutProvider}
            onChange={(e) => setPayoutProvider(e.target.value as "MTN" | "AIRTEL")}
          >
            <option value="MTN">MTN MoMo</option>
            <option value="AIRTEL">Airtel Money</option>
          </select>
        </FormField>

        <FormField label="Payout mobile number" required error={fieldErrors.payout_account}>
          <PhoneInput value={payoutAccount} onChange={setPayoutAccount} />
        </FormField>
      </section>

      <button onClick={handleRegister} disabled={submitting} className="btn-primary w-full py-3">
        {submitting ? "Submitting..." : "Submit for Review"}
      </button>
    </div>
  );
};

export default VendorStorePage;
