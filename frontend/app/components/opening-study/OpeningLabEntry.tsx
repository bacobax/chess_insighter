import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { Button } from "~/components/ui/button";

/** Player-dossier card that opens the Opening Lab tree. The tree is general,
 *  so it needs no report; `username` only lets Back return to this dossier. */
export function OpeningLabEntry({ username }: { username: string }) {
  const base = `/opening-study?username=${encodeURIComponent(username)}`;

  return (
    <div className="tp-feature">
      <div>
        <p className="folio">Interactive study tree</p>
        <h2>Build a repertoire around what you want from an opening.</h2>
        <p>Pick a side, then expand moves one level at a time. Your moves are ranked by sharpness, how systematic they are and how much theory they need. Opponent replies are ordered by engine strength or by how often people play them.</p>
        <div className="tp-actions" style={{ marginTop: "1.75rem" }}>
          <Link to={base}><Button style={{ background: "var(--accent)", color: "#0a0e0b" }}>Open the Opening Lab <ArrowRight /></Button></Link>
          <Link to={`${base}&color=white`}><Button variant="ghost">As White</Button></Link>
          <Link to={`${base}&color=black`}><Button variant="ghost">As Black</Button></Link>
        </div>
      </div>
      <ol className="tp-trio">
        <li><span>01</span><div><b>A quick setup</b><small>A few questions set every filter the first time you open it</small></div></li>
        <li><span>02</span><div><b>A feasibility check</b><small>Only moves that are engine-sound or practically tricky make the cut</small></div></li>
        <li><span>03</span><div><b>Your own ranking</b><small>Fine-tune sharpness, systems and memory load at any time</small></div></li>
      </ol>
    </div>
  );
}
