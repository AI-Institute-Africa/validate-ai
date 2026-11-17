// Draft translations (Shona, Ndebele) are shown only after a fluent reviewer signs them off.
// Until then the English text is used, so a wrong word never reaches a payer. Staging or a
// demo can opt in with VITE_ALLOW_UNREVIEWED_TRANSLATIONS=true or a local switch.

export type Lang = "en" | "sn" | "nd";

export const REVIEWED: Record<Lang, boolean> = { en: true, sn: false, nd: false };

// Per-string sign-off by a fluent reviewer. A language is switched on as a whole (REVIEWED above) only when
// every string is signed off; until then, an individually signed-off string can already be shown.
// Add a key here ONLY after a fluent speaker has approved that exact text.
export const REVIEWED_KEYS: Record<Lang, ReadonlySet<string>> = { en: new Set(), sn: new Set(), nd: new Set() };

// Drafts a reviewer or audit found wrong. They are kept out of the live dictionaries (English shows
// instead) and listed here so the next reviewer sees what not to repeat.
export const FLAGGED_DRAFTS: Record<Lang, Record<string, { text: string; why: string }>> = {
  en: {},
  sn: {
    "hero.title": { text: "Chenjedza kubhadhara", why: "Uses 'Chenjedza', which reads as 'be careful / beware', for 'verify' (audit note, not confirmed by a fluent speaker)" },
    "form.trust": { text: "Risiti yako inonyengera. Inongoti chibvunzo chete — inochinjwa nemari yanga yanga yakapihwa chete.", why: "Back-translates as 'your receipt deceives / is deceptive', the opposite of the English meaning (audit note)" },
  },
  nd: {
    "form.trust": { text: "Irekhodi lakho liqinisekiswa. Liyisicelo kuphela — liyaqinisekiswa ngemali engeniswe kuphela.", why: "Says the record 'is confirmed', which is the opposite of the English 'treated as untrusted evidence' (audit note)" },
    "result.green.note": { text: "Umbala okuluhlaza ushoko lokuthi irekhodi lifundwe kahle futhi lihambisana ngenye imali — ukuvuma okugcwele kusengathi kubhange.", why: "Reads as garbled; the meaning of the English sentence is lost (audit note)" },
  },
};

export function translationActive(lang: Lang, allowDrafts: boolean, reviewed: Record<Lang, boolean> = REVIEWED): boolean {
  return lang === "en" || reviewed[lang] || allowDrafts;
}

export function translate(
  lang: Lang,
  key: string,
  dicts: Record<Lang, Record<string, string>>,
  allowDrafts: boolean,
  reviewed: Record<Lang, boolean> = REVIEWED,
  reviewedKeys: Record<Lang, ReadonlySet<string>> = REVIEWED_KEYS,
): string {
  if (translationActive(lang, allowDrafts, reviewed)) return dicts[lang][key] ?? dicts.en[key] ?? key;
  // the language is not live yet, but this one string may be signed off
  if (reviewedKeys[lang].has(key) && dicts[lang][key] !== undefined) return dicts[lang][key];
  return dicts.en[key] ?? key;
}

export type Coverage = {
  total: number;
  translated: number; // a draft or final text exists
  reviewed: number; // signed off by a fluent reviewer
  missing: string[]; // English only so far
  live: boolean; // every string signed off, so the whole language can be switched on
};

export function coverage(
  lang: Lang,
  en: Record<string, string>,
  dict: Record<string, string>,
  reviewedKeys: ReadonlySet<string>,
): Coverage {
  const keys = Object.keys(en);
  const translated = keys.filter((k) => dict[k] !== undefined);
  const reviewed = keys.filter((k) => dict[k] !== undefined && reviewedKeys.has(k));
  return {
    total: keys.length,
    translated: translated.length,
    reviewed: reviewed.length,
    missing: keys.filter((k) => dict[k] === undefined),
    live: lang === "en" || reviewed.length === keys.length,
  };
}

/** Keys missing from a language, and keys whose {placeholders} differ from English. */
export function parityProblems(en: Record<string, string>, other: Record<string, string>): string[] {
  const holes = (s: string) => (s.match(/\{[a-z_]+\}/gi) ?? []).sort().join(",");
  const out: string[] = [];
  for (const [k, v] of Object.entries(en)) {
    if (!(k in other)) out.push(`missing: ${k}`);
    else if (holes(v) !== holes(other[k])) out.push(`placeholders differ: ${k}`);
  }
  return out;
}
