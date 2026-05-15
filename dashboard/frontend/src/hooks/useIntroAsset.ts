import { useEffect, useState } from "react";

export type IntroAsset =
  | { kind: "video"; src: string }
  | { kind: "image"; src: string }
  | { kind: "none" };

/**
 * Looks for a user-supplied hero asset in /public/intro/ and, if found, lets
 * IntroSequence composite it as the photoreal hero layer instead of the
 * built 2.5D circuit.
 *
 * Drop a file named one of these into dashboard/frontend/public/intro/:
 *   hero.mp4 | hero.webm   -> used as a muted autoplay video
 *   hero.jpg | hero.png    -> used as a Ken-Burns hero still
 *
 * Nothing there? The hook returns { kind: "none" } and the cinematic 2.5D
 * scene plays. No config, no rebuild — just add the file.
 */
const CANDIDATES: Array<{ path: string; kind: "video" | "image" }> = [
  { path: "/intro/hero.mp4", kind: "video" },
  { path: "/intro/hero.webm", kind: "video" },
  { path: "/intro/hero.jpg", kind: "image" },
  { path: "/intro/hero.jpeg", kind: "image" },
  { path: "/intro/hero.png", kind: "image" },
];

export function useIntroAsset(): { asset: IntroAsset; resolved: boolean } {
  const [asset, setAsset] = useState<IntroAsset>({ kind: "none" });
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function probe() {
      for (const c of CANDIDATES) {
        try {
          const res = await fetch(c.path, { method: "GET", cache: "no-store" });
          if (cancelled) return;
          // IMPORTANT: dev servers (Vite) do SPA-fallback — a missing
          // /intro/hero.mp4 still returns 200 with index.html. So we must
          // verify the *content-type* actually is a media file, never trust
          // the extension or the 200 alone.
          const type = (res.headers.get("content-type") || "").toLowerCase();
          const isMedia =
            c.kind === "video"
              ? type.startsWith("video/")
              : type.startsWith("image/");
          if (res.ok && isMedia) {
            setAsset({ kind: c.kind, src: c.path });
            setResolved(true);
            return;
          }
        } catch {
          // ignore — try the next candidate
        }
      }
      if (!cancelled) {
        setAsset({ kind: "none" });
        setResolved(true);
      }
    }

    probe();
    return () => {
      cancelled = true;
    };
  }, []);

  return { asset, resolved };
}
