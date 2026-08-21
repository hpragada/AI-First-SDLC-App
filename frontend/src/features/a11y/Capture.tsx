// The captured screen, with the failing element ringed.
//
// **Its own file because two screens draw it**: the review console (S-36), where a person is
// deciding, and the read-only finding view (S-39), where a person is looking. They ask the same
// question of the same picture, and two copies of this arithmetic would eventually disagree
// about where the box goes — which is the one thing a piece of evidence may not do.
import { useState } from "react";

import { Button, Skeleton, cx } from "../../components/ui";
import type { A11yReviewFinding } from "../../types";
import { useA11yCapture } from "./hooks";

// Two modes because a reviewer needs both: FIT to judge the layout, ACTUAL to judge the pixels —
// contrast and focus rings are not decidable on a scaled-down image, and those are most of what
// this reviewer is deciding.
export function Capture({ projectId, item }: { projectId: string; item: A11yReviewFinding }) {
  const [fit, setFit] = useState(true);
  const [natural, setNatural] = useState<{ w: number; h: number } | undefined>();
  const kind: "page" | "element" = item.page_image ? "page" : "element";
  const available = item.page_image || item.element_image;
  const { url, error } = useA11yCapture(projectId, item.id, kind, available);

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
  const marker = kind === "page" && item.box && natural;

  return (
    <div className="shot" style={{ marginTop: "var(--space-4)" }}>
      <div className={cx("shot__stage", fit && "shot__stage--fit")}>
        {url ? (
          <>
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
          </>
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
