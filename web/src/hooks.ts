import { useCallback, useEffect, useRef, useState } from "react";

/** useState that is remembered in localStorage (if the browser allows it). */
export function useStoredState(key: string, initial: () => string) {
  const [value, setValue] = useState<string>(() => {
    try {
      return localStorage.getItem(key) ?? initial();
    } catch {
      return initial();
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* storage blocked: keep it in memory only */
    }
  }, [key, value]);
  return [value, setValue] as const;
}

export interface ToastState {
  text: string;
  bad: boolean;
  visible: boolean;
}

/** A small message at the bottom of the screen. */
export function useToast() {
  const [toast, setToast] = useState<ToastState>({ text: "", bad: false, visible: false });
  const timer = useRef<number | undefined>(undefined);
  const notify = useCallback((text: string, bad = false) => {
    setToast({ text, bad, visible: true });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast((t) => ({ ...t, visible: false })), 3500);
  }, []);
  return { toast, notify };
}

export type Notify = (text: string, bad?: boolean) => void;
