import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Language = "vi" | "en";

interface LangState {
  lang: Language;
  setLang: (lang: Language) => void;
}

export const useLangStore = create<LangState>()(
  persist(
    (set) => ({
      lang: "vi",
      setLang: (lang) => set({ lang }),
    }),
    { name: "chatgpt2api-lang" }
  )
);
