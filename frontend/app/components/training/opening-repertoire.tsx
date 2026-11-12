import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { RepertoireWorkspace } from "~/components/repertoire/RepertoireWorkspace";
import type { RepertoireColor, TrainingOpeningRecommendation } from "~/lib/types";

/** Where each training-plan slot starts: Black's slots begin after White's first move. */
const SLOT_START: Record<string, { color: RepertoireColor; start: string[] }> = {
  white: { color: "white", start: [] },
  black_vs_e4: { color: "black", start: ["e2e4"] },
  black_vs_d4: { color: "black", start: ["d2d4"] },
  black_vs_other: { color: "black", start: [] },
};

/**
 * The plan's openings, drilled from your saved repertoire (the same one as the
 * Opening Lab's Repertoire view). An empty repertoire is filled from the plan's
 * lines first; you can change any move in Build mode.
 */
export function OpeningRepertoire({ openings }: { openings: TrainingOpeningRecommendation[] }) {
  const [active, setActive] = useState(0);
  const opening = openings[active];
  if (!opening) return <p className="tp-empty">No openings in this plan yet.</p>;
  const slot = SLOT_START[opening.slot] ?? SLOT_START.white;
  const seedLines = openings.filter((item) => (SLOT_START[item.slot] ?? SLOT_START.white).color === slot.color).map((item) => item.line);

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div>
        <p className="folio">Opening drill</p>
        <h2 className="tp-panel-title">Play your side from memory.</h2>
        <p className="tp-note" style={{ margin: ".5rem 0 0" }}>
          Your repertoire is shared with the Opening Lab. Drill its lines here, or switch to Build to choose your move wherever a line still needs one.
        </p>
      </div>
      <div className="tp-tabs" role="tablist" aria-label="Openings">
        {openings.map((item, index) => (
          <button key={item.slot} type="button" role="tab" aria-selected={index === active} onClick={() => setActive(index)}>
            <small>{item.slot_label}</small>
            <b>{item.name.split(" · ")[0]}</b>
          </button>
        ))}
      </div>
      {opening.plans || opening.trap ? (
        <dl className="tp-kv">
          {opening.plans ? <><dt>Plans</dt><dd>{opening.plans}</dd></> : null}
          {opening.trap ? <><dt>Trap</dt><dd>{opening.trap}</dd></> : null}
        </dl>
      ) : null}
      <RepertoireWorkspace
        key={opening.slot}
        color={slot.color}
        startPrefixUci={slot.start}
        seedLines={seedLines}
        autoSeed
        initialMode="drill"
        labLink
      />
      <p className="tp-note" style={{ margin: 0 }}><CheckCircle2 className="inline h-3.5 w-3.5" /> {opening.why}</p>
    </div>
  );
}
