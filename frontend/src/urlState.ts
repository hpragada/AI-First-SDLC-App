/**
 * A list screen's selection, seeded from the URL.
 *
 * Deep-linking to one row is only half of `links.ts` — the destination has to honour the param.
 * This is the smallest hook that does that without changing how any screen behaves when no param
 * is present.
 *
 * It deliberately does NOT write back to the URL as the user clicks around: deep-linkability in,
 * no URL rewriting out. Rewriting on every selection would fill the back button with noise and
 * make "go back" mean "undo one click".
 */
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * `[value, setValue, pinned]` — `pinned` is true while the value came from the URL and the user
 * has not chosen something else, which is what lets a screen say "this is the one you asked for"
 * (or "…and it is no longer here").
 */
export function useParamState(
  name: string,
  fallback = "",
): [string, (next: string) => void, boolean] {
  const [params] = useSearchParams();
  const fromUrl = params.get(name) ?? "";
  const [value, setValue] = useState(fromUrl || fallback);
  const [pinned, setPinned] = useState(Boolean(fromUrl));
  // Track what the URL last said, so a URL change while mounted re-seeds the selection but a
  // local change does not fight it. Without this the screen would either ignore navigation to a
  // second deep link or loop between the two sources.
  const lastFromUrl = useRef(fromUrl);

  useEffect(() => {
    if (fromUrl === lastFromUrl.current) return;
    lastFromUrl.current = fromUrl;
    if (fromUrl) {
      setValue(fromUrl);
      setPinned(true);
    } else {
      setPinned(false);
    }
  }, [fromUrl]);

  const choose = (next: string) => {
    setValue(next);
    setPinned(false); // the user picked; stop claiming the URL asked for this
  };
  return [value, choose, pinned];
}
