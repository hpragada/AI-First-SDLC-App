// The captured screen, with the failing element ringed.
//
// **Its own file because two screens draw it**: the review console (S-36), where a person is
// deciding, and the read-only finding view (S-39), where a person is looking. They ask the same
// question of the same picture, and two copies of this arithmetic would eventually disagree
// about where the box goes — which is the one thing a piece of evidence may not do.
import { useEffect, useRef, useState } from "react";

import { Button, Skeleton, cx } from "../../components/ui";
import type { A11yReviewFinding } from "../../types";
import { useA11yCapture } from "./hooks";

// Two modes because a reviewer needs both: FIT to judge the layout, ACTUAL to judge the pixels —
// contrast and focus rings are not decidable on a scaled-down image, and those are most of what
// this reviewer is deciding.
export function Capture({ projectId, item }: { projectId: string; item: A11yReviewFinding }) {
  const [fit, setFit] = useState(true);
  const [natural, setNatural] = useState<{ w: number; h: number } | undefined>();
  const stageRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLSpanElement>(null);
  const kind: "page" | "element" = item.page_image ? "page" : "element";
  const available = item.page_image || item.element_image;
  const { url, error } = useA11yCapture(projectId, item.id, kind, available);

  // Bring the ringed element into view. A full-page capture is routinely three to six screens
  // tall inside a 340px window, so a correctly placed ring is still a ring the reviewer has to
  // go looking for — and the one below the fold reads as "there is no ring on this one".
  //
  // The scroll is set on the STAGE directly rather than with `scrollIntoView`, which walks every
  // scrollable ancestor and would drag the whole review console up to meet it.
  useEffect(() => {
    const stage = stageRef.current;
    const ring = ringRef.current;
    if (!stage || !ring) return;
    // `offsetTop`/`offsetLeft` are measured against `.shot__frame`, which sits at the origin of
    // the stage's scrollable content — so they are already the distance to scroll to.
    stage.scrollTop = Math.max(0, ring.offsetTop - (stage.clientHeight - ring.offsetHeight) / 2);
    stage.scrollLeft = Math.max(0, ring.offsetLeft - (stage.clientWidth - ring.offsetWidth) / 2);
    // `natural` is the signal that the image has loaded and laid out; `fit` changes the scale, so
    // the arithmetic has to run again. `url` covers moving between findings without unmounting.
  }, [natural, fit, url]);

  if (!available || error) {
    return (
      <div className="shot shot--missing" style={{ marginTop: "var(--space-4)" }}>
        <div className="shot__stage">
          <strong>There is no picture of this one</strong>
          {/* Never a bare empty frame. A missing capture is a fact with a cause, and saying
              which cause is the difference between "we could not" and "nothing was wrong". */}
          <span className="t-sm">
            {error ?? item.capture_reason ?? "no capture was kept for this element"}
          </span>
          <span className="t-xs u-muted">
            You can still judge it from the element, the criterion and what the check saw.
          </span>
        </div>
      </div>
    );
  }

  // The box is in the page screenshot's own pixel space — the capture records
  // `getBoundingClientRect()` plus the scroll offset and the shot is full-page, so the two share
  // one coordinate system. Positioned as a PERCENTAGE of the image's natural size, which lands
  // correctly in FIT (image scaled to the panel) and in ACTUAL (1:1, scrolling) with no
  // per-mode arithmetic. Drawn only over the page: on an element crop the crop IS the element,
  // and a ring around the whole picture would say nothing.
  //
  // **The percentages are only meaningful against the PICTURE**, which is why the ring lives
  // inside `.shot__frame` rather than straight in the stage. A percentage on an absolutely
  // positioned element resolves against its containing block, and the stage's height is clamped
  // (`max-height: 340px`) while a full-page capture renders several times taller. Measured on a
  // real 1280x1144 shot in this panel: the ring landed 237.8px down where it belonged at 461.3px
  // and was drawn at half height — every capture off by exactly the clamp ratio, on every
  // finding this platform has ever shown. The frame hugs the image, so the two agree by
  // construction, in both modes, without either of them knowing about the other.
  const marker = kind === "page" && item.box && natural;

  return (
    <div className="shot" style={{ marginTop: "var(--space-4)" }}>
      <div ref={stageRef} className={cx("shot__stage", fit && "shot__stage--fit")}>
        {url ? (
          // Hugs the image and nothing else — see `marker` above for what depends on that.
          <span className="shot__frame">
            <img
              className="shot__img"
              src={url}
              alt={`Captured screen ${item.route}`}
              onLoad={(e) =>
                setNatural({
                  w: e.currentTarget.naturalWidth,
                  h: e.currentTarget.naturalHeight,
                })
              }
            />
            {marker && (
              <span
                ref={ringRef}
                className="shot__marker"
                data-label={item.selector}
                style={{
                  left: `${(item.box!.x / natural!.w) * 100}%`,
                  top: `${(item.box!.y / natural!.h) * 100}%`,
                  width: `${(item.box!.width / natural!.w) * 100}%`,
                  height: `${(item.box!.height / natural!.h) * 100}%`,
                }}
              />
            )}
          </span>
        ) : (
          <Skeleton kind="block" />
        )}
      </div>
      <div className="shot__bar">
        <span>{fit ? "Fit to width" : "Actual size"}</span>
        <Button variant="ghost" size="sm" onClick={() => setFit((v) => !v)}>
          {fit ? "View actual size" : "Fit to width"}
        </Button>
        <span className="u-spacer" />
        {natural && (
          <span className="shot__dims">
            {natural.w} × {natural.h}
          </span>
        )}
      </div>
    </div>
  );
}
