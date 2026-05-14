import { useEffect, useRef, useState } from "react";
import { fetchSnapshot, type Snapshot } from "../lib/api";

interface State {
  snapshot: Snapshot | null;
  online: boolean;
  ageMs: number;
}

export function useTelemetry(intervalMs = 2500): State {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState<boolean>(false);
  const [ageMs, setAgeMs] = useState<number>(0);
  const lastFetchRef = useRef<number>(Date.now());

  useEffect(() => {
    let cancelled = false;

    async function pull() {
      try {
        const data = await fetchSnapshot();
        if (cancelled) return;
        setSnapshot(data);
        setOnline(true);
        lastFetchRef.current = Date.now();
      } catch {
        if (cancelled) return;
        setOnline(false);
      }
    }

    pull();
    const id = setInterval(pull, intervalMs);
    const aid = setInterval(
      () => setAgeMs(Date.now() - lastFetchRef.current),
      250,
    );
    return () => {
      cancelled = true;
      clearInterval(id);
      clearInterval(aid);
    };
  }, [intervalMs]);

  return { snapshot, online, ageMs };
}
