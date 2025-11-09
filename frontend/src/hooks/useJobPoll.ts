// src/hooks/useJobPoll.ts
import { useEffect, useRef } from "react";

const BACKEND = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function useJobPoll(
  jobId: number | null,
  onFinished: (jobResult: any) => void,
  intervalMs = 1500
) {
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND}/jobs/status/${jobId}`);
        if (!res.ok) {
          // keep polling on transient errors
          console.warn("job poll status", res.status);
          if (!cancelled) timerRef.current = window.setTimeout(poll, intervalMs);
          return;
        }
        const json = await res.json();
        if (json.status === "finished" || json.status === "error") {
          if (!cancelled) onFinished(json);
        } else {
          if (!cancelled) timerRef.current = window.setTimeout(poll, intervalMs);
        }
      } catch (err) {
        console.error("poll error", err);
        if (!cancelled) timerRef.current = window.setTimeout(poll, intervalMs);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [jobId, onFinished, intervalMs]);
}
