import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, post } from "../api";
import { demoInfo, prepareKyc, sampleFile } from "../demo";
import { DOC_TYPES } from "../labels";
import { useI18n } from "../i18n";
import { useToast } from "../toast";
import { Chip, PageHeader, StateChip } from "../ui";

type Out = { kyc_id: string; state: string; message: string | null; subject_type: string; subject_ref: string };
type Status = { verified: boolean; state: string | null; expires_at?: string | null };

const SAMPLES: { id: string; label: string; hint: string }[] = [
  { id: "clear", label: "Valid ID card", hint: "Should verify automatically" },
  { id: "passport", label: "Passport (MRZ)", hint: "Check digits validate" },
  { id: "mismatch", label: "Wrong selfie", hint: "Face does not match" },
  { id: "expired", label: "Expired ID", hint: "Needs a reviewer" },
  { id: "edited", label: "Edited passport", hint: "Printed vs checked zone" },
  { id: "noface", label: "No face in selfie", hint: "Asked to retake" },
];

const NEXT_STATES = ["VERIFIED", "NEEDS_REVIEW", "NEEDS_INFORMATION", "REJECTED"];

function Drop({ label, hint, file, onFile, optional }: { label: string; hint: string; file: File | null; onFile: (f: File | null) => void; optional?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const { t } = useI18n();
  const [over, setOver] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) return setUrl(null);
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return (
    <div
      className={`dz${file ? " has" : ""}${over ? " over" : ""}`}
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files?.[0] ?? null); }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
    >
      <span className="ph">{url ? <img src={url} alt="" /> : "📷"}</span>
      <span style={{ flex: 1 }}>
        <b>{label} {optional && <span className="muted small">{t("kyc.optional")}</span>}</b>
        <span className="muted small">{file ? file.name : hint}</span>
      </span>
      {file && (
        <button type="button" className="ghost small" onClick={(e) => { e.stopPropagation(); onFile(null); }}>
          {t("kyc.remove")}
        </button>
      )}
      <input ref={input} type="file" accept="image/*" hidden onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </div>
  );
}

export default function Kyc() {
  const { t } = useI18n();
  const toast = useToast();
  const demo = demoInfo();
  const [subjectType, setSubjectType] = useState("payer");
  const [subjectRef, setSubjectRef] = useState("");
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);
  const [result, setResult] = useState<Out | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [lookup, setLookup] = useState("");

  const sample = useMutation({
    mutationFn: async (variant: string) => {
      const s = await prepareKyc(variant);
      const [f, sf] = await Promise.all([sampleFile(s.front_url, "id-front.png"), sampleFile(s.selfie_url, "selfie.png")]);
      return { s, f, sf };
    },
    onSuccess: ({ s, f, sf }) => {
      setSubjectType("payer");
      setSubjectRef(s.subject_ref);
      setFront(f);
      setSelfie(sf);
      setBack(null);
      setNote(s.note);
      setResult(null);
    },
    onError: (e) => toast("err", (e as Error).message),
  });

  const status = useQuery({
    queryKey: ["kyc-status", subjectType, lookup],
    enabled: lookup.trim().length > 0,
    queryFn: () => api<Status>(`/kyc/subjects/${subjectType}/${encodeURIComponent(lookup.trim())}/status`),
  });

  const submit = useMutation({
    mutationFn: () => {
      if (!front || !selfie) throw new Error(t("kyc.err.photos"));
      const fd = new FormData();
      fd.append("subject_type", subjectType);
      if (subjectRef.trim()) fd.append("subject_ref", subjectRef.trim());
      fd.append("front", front);
      fd.append("selfie", selfie);
      if (back) fd.append("back", back);
      return post<Out>("/kyc/verifications", fd);
    },
    onSuccess: (r) => {
      setResult(r);
      setLookup(r.subject_ref);
    },
    onError: (e) => toast("err", (e as Error).message),
  });

  return (
    <div>
      <PageHeader
        title={t("kyc.title")}
        sub={t("kyc.sub")}
      />
      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <div className="card">
          {demo && (
            <>
              <h3>Try a sample</h3>
              <div className="sample-row">
                {SAMPLES.map((s) => (
                  <button key={s.id} type="button" className="secondary" title={s.hint} disabled={sample.isPending} onClick={() => sample.mutate(s.id)}>
                    {s.label}
                  </button>
                ))}
              </div>
              {note && <p className="learn" style={{ marginTop: 0 }}><b>This sample:</b> {note}</p>}
            </>
          )}
          <h3>{t("kyc.who")}</h3>
          <div className="inline-pair" style={{ marginBottom: 10 }}>
            <select value={subjectType} onChange={(e) => setSubjectType(e.target.value)} aria-label={t("kyc.who")}>
              <option value="payer">{t("kyc.who.payer")}</option>
              <option value="staff">{t("kyc.who.staff")}</option>
              <option value="org">{t("kyc.who.org")}</option>
            </select>
            {subjectType !== "staff" && (
              <input placeholder={t("kyc.ref")} value={subjectRef} onChange={(e) => setSubjectRef(e.target.value)} aria-label={t("kyc.ref")} />
            )}
          </div>
          <Drop label={t("kyc.front.label")} hint={t("kyc.front.hint")} file={front} onFile={setFront} />
          <Drop label={t("kyc.back.label")} hint={t("kyc.back.hint")} file={back} onFile={setBack} optional />
          <Drop label={t("kyc.selfie.label")} hint={t("kyc.selfie.hint")} file={selfie} onFile={setSelfie} />
          <button type="button" className="lg" disabled={submit.isPending || !front || !selfie} onClick={() => submit.mutate()}>
            {submit.isPending ? t("kyc.checking") : t("kyc.submit")}
          </button>
        </div>

        <div>
          <div className="card" aria-live="polite">
            <h3>{t("kyc.result")}</h3>
            {!result && !submit.isPending && <p className="muted">{t("kyc.result.empty")}</p>}
            {submit.isPending && (
              <ul className="checks">
                {[t("kyc.step1"), t("kyc.step2"), t("kyc.step3"), t("kyc.step4")].map((text, i) => (
                  <li key={i} className="story" style={{ animationDelay: `${i * 500}ms`, display: "flex" }}>
                    <span className="mk na">…</span>
                    {text}
                  </li>
                ))}
              </ul>
            )}
            {result && (
              <>
                <p><StateChip state={result.state} /></p>
                <p>{NEXT_STATES.includes(result.state) ? t(`kyc.next.${result.state}`) : result.state}</p>
                {result.message && <div className="bubble">{result.message}</div>}
              </>
            )}
          </div>
          <div className="card">
            <h3>{t("kyc.tips.title")}</h3>
            <ul className="small muted">
              <li>{t("kyc.tip1")}</li>
              <li>{t("kyc.tip2")}</li>
              <li>{t("kyc.tip3")}</li>
              <li>{t("kyc.tip4").replace("{types}", Object.keys(DOC_TYPES).map((k) => t(`doc.${k}`)).join(", "))}</li>
            </ul>
          </div>
          <div className="card">
            <h3>{t("kyc.lookup.title")}</h3>
            <input placeholder={t("kyc.ref")} value={lookup} onChange={(e) => setLookup(e.target.value)} aria-label={t("kyc.lookup.ref")} />
            {status.data && (
              <p style={{ marginTop: 10 }}>
                {status.data.verified ? <Chip tone="ok">{t("kyc.verified")}</Chip> : <Chip tone="neutral">{t("kyc.notverified")}</Chip>}
                {status.data.state && <span className="muted small"> {t("kyc.latest").replace("{state}", t(`state.${status.data.state}`))}</span>}
                {status.data.expires_at && <span className="muted small"> · {t("kyc.valid").replace("{date}", new Date(status.data.expires_at).toLocaleDateString())}</span>}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
