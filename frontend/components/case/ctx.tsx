"use client";
import { createContext, ReactNode, useContext } from "react";

export type Src = { f?: string; l?: number; n?: number };
export type CaseCtxT = {
  c: any;
  reload: () => Promise<void>;
  tab: string;
  setTab: (t: string) => void;
  canEdit: boolean;
  isSho: boolean;
  locked: boolean;
  segments: any[];
  reloadNarration: () => Promise<void>;
  openSrc: (s: Src) => void;
};
const CaseCtx = createContext<CaseCtxT | null>(null);

export function CaseProvider({ value, children }: { value: CaseCtxT; children: ReactNode }) {
  return <CaseCtx.Provider value={value}>{children}</CaseCtx.Provider>;
}

export function useCaseMaybe() {
  return useContext(CaseCtx);
}

export function useCase() {
  const c = useContext(CaseCtx);
  if (!c) throw new Error("useCase outside provider");
  return c;
}
