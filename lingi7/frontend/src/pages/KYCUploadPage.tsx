/**
 * KYCUploadPage — NRC front/back photo submission
 *
 * Zambian compliance: Bank of Zambia KYC rules require NRC verification
 * for all users transacting on the platform.
 */

import React, { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store";
import { extractMessage, isValidNrcNumber, ZAMBIA_PROVINCES } from "../utils";

type UploadStep = "intro" | "upload" | "submitting" | "success" | "error";

const KYCUploadPage: React.FC = () => {
  const navigate = useNavigate();
  const { setUser } = useAuthStore();

  const [step, setStep] = useState<UploadStep>("intro");
  const [nrcNumber, setNrcNumber] = useState("");
  const [physicalAddress, setPhysicalAddress] = useState("");
  const [province, setProvince] = useState("");
  const [nrcFront, setNrcFront] = useState<File | null>(null);
  const [nrcBack, setNrcBack] = useState<File | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const frontRef = useRef<HTMLInputElement>(null);
  const backRef = useRef<HTMLInputElement>(null);
  const selfieRef = useRef<HTMLInputElement>(null);

  const handleFile = (
    setter: (f: File | null) => void
  ) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file && file.size > 10 * 1024 * 1024) {
      setErrorMsg("File too large. Maximum size is 10MB.");
      return;
    }
    setter(file);
    setErrorMsg(null);
  };

  const handleSubmit = async () => {
    if (!nrcNumber.trim() || !physicalAddress.trim() || !province.trim()) {
      setErrorMsg("NRC number, address, and province are required.");
      return;
    }
    if (!isValidNrcNumber(nrcNumber)) {
      setErrorMsg("NRC must be in format XXXXXX/YY/Z (e.g. 123456/78/1).");
      return;
    }
    if (!nrcFront || !nrcBack || !selfie) {
      setErrorMsg("All three photos are required.");
      return;
    }
    setStep("submitting");
    const formData = new FormData();
    formData.append("nrc_number", nrcNumber.trim());
    formData.append("physical_address", physicalAddress.trim());
    formData.append("province", province.trim());
    formData.append("nrc_front", nrcFront);
    formData.append("nrc_back", nrcBack);
    formData.append("selfie", selfie);

    try {
      await authApi.submitKYC(formData);
      // Refresh user so KYC status updates
      const updated = await authApi.me();
      setUser(updated);
      setStep("success");
    } catch (err) {
      setErrorMsg(extractMessage(err));
      setStep("error");
    }
  };

  if (step === "success") {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <div className="text-5xl mb-4">✅</div>
        <h2 className="text-xl font-bold text-gray-900">Documents Submitted</h2>
        <p className="mt-2 text-sm text-gray-500">
          Your KYC documents are under review. This usually takes 24–48 hours.
          You'll be notified via SMS once verified.
        </p>
        <button
          onClick={() => navigate("/account")}
          className="btn-primary mt-6"
        >
          Back to Account
        </button>
      </div>
    );
  }

  if (step === "submitting") {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
        <p className="text-sm text-gray-500">Uploading documents securely...</p>
      </div>
    );
  }

  if (step === "intro") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 space-y-5 sm:px-6">
        <button
          onClick={() => navigate("/account")}
          className="text-sm text-gray-500 min-h-0"
        >
          ← Back
        </button>
        <p className="text-sm font-bold tracking-[.16em] text-blue-600">ACCOUNT SECURITY</p>
        <h1 className="text-4xl font-black tracking-tight text-slate-950">Verify your identity.</h1>

        <div className="card p-5 space-y-3">
          <p className="text-sm font-semibold text-gray-800">Why we need this</p>
          <p className="text-sm text-gray-600">
            To comply with Bank of Zambia KYC regulations and protect all users
            on the platform, we verify your identity using your National
            Registration Card (NRC).
          </p>
          <p className="text-sm text-gray-600">
            Your documents are encrypted at rest, stored in Zambia, and never
            shared with third parties. Protected under the Data Protection Act 2021.
          </p>
        </div>

        <div className="card p-5">
          <p className="text-sm font-semibold text-gray-800 mb-3">You'll need:</p>
          <ul className="space-y-2 text-sm text-gray-600">
            {[
              "📋 NRC front photo — clear, well-lit, no glare",
              "📋 NRC back photo — same requirements",
              "🤳 Selfie — holding your NRC next to your face",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <button
          onClick={() => setStep("upload")}
          className="btn-primary w-full py-3"
        >
          Continue
        </button>
      </div>
    );
  }

  // Upload step
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-5 sm:px-6">
      <button
        onClick={() => setStep("intro")}
        className="text-sm text-gray-500 min-h-0"
      >
        ← Back
      </button>
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">ACCOUNT SECURITY</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">Upload documents.</h1>

      {errorMsg && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      <div className="card p-4 space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            NRC Number
          </label>
          <input
            value={nrcNumber}
            onChange={(e) => setNrcNumber(e.target.value)}
            placeholder="123456/78/1"
            className="input"
          />
          <p className="mt-1 text-xs text-gray-500">
            Format: XXXXXX/YY/Z (e.g. 123456/78/1)
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Physical Address
          </label>
          <textarea
            value={physicalAddress}
            onChange={(e) => setPhysicalAddress(e.target.value)}
            rows={3}
            placeholder="House No, Street, Area, Town/City"
            className="input"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Province
          </label>
          <select
            value={province}
            onChange={(e) => setProvince(e.target.value)}
            className="input"
          >
            <option value="">Select province</option>
            {ZAMBIA_PROVINCES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-4">
        <PhotoUploadCard
          label="NRC Front"
          description="Photo of the front of your NRC"
          file={nrcFront}
          inputRef={frontRef}
          onChange={handleFile(setNrcFront)}
        />
        <PhotoUploadCard
          label="NRC Back"
          description="Photo of the back of your NRC"
          file={nrcBack}
          inputRef={backRef}
          onChange={handleFile(setNrcBack)}
        />
        <PhotoUploadCard
          label="Selfie with NRC"
          description="Hold your NRC next to your face"
          file={selfie}
          inputRef={selfieRef}
          onChange={handleFile(setSelfie)}
          accept="image/*"
          capture="user"
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={
          !nrcNumber.trim() ||
          !physicalAddress.trim() ||
          !province.trim() ||
          !nrcFront ||
          !nrcBack ||
          !selfie
        }
        className="btn-primary w-full py-3 disabled:opacity-50"
      >
        Submit Documents
      </button>

      <p className="text-center text-xs text-gray-400">
        🔒 Documents encrypted in transit and at rest · DPA 2021 compliant
      </p>
    </div>
  );
};

// ── PhotoUploadCard ───────────────────────────────────────────────────────────

interface PhotoCardProps {
  label: string;
  description: string;
  file: File | null;
  inputRef: React.RefObject<HTMLInputElement>;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  accept?: string;
  capture?: "user" | "environment";
}

const PhotoUploadCard: React.FC<PhotoCardProps> = ({
  label,
  description,
  file,
  inputRef,
  onChange,
  accept = "image/*",
  capture,
}) => {
  const preview = file ? URL.createObjectURL(file) : null;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-semibold text-gray-800">{label}</p>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
        {file && (
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            ✓ Ready
          </span>
        )}
      </div>

      {preview && (
        <img
          src={preview}
          alt={`${label} preview`}
          className="mb-3 h-32 w-full rounded-lg object-cover"
        />
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        capture={capture}
        onChange={onChange}
        className="hidden"
      />
      <button
        onClick={() => inputRef.current?.click()}
        className="w-full rounded-lg border-2 border-dashed border-gray-300 py-3 text-sm font-medium text-gray-600 hover:border-emerald-400 hover:text-emerald-600 transition-colors min-h-0"
      >
        {file ? "Change Photo" : "Choose Photo / Take Camera Shot"}
      </button>
    </div>
  );
};

export default KYCUploadPage;
