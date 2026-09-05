import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Check, Loader2, X } from "lucide-react";
import { Button } from "~/components/ui/button";
import { verifyEmail } from "~/lib/api";

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");
  const attemptedToken = useRef<string | null>(null);
  useEffect(() => {
    const token = searchParams.get("token");
    window.history.replaceState({}, document.title, "/verify-email");
    if (!token) { setMessage("This verification link is incomplete."); setState("error"); return; }
    if (attemptedToken.current === token) return;
    attemptedToken.current = token;
    verifyEmail(token)
      .then(() => setState("success"))
      .catch((err) => { setMessage(err instanceof Error ? err.message : "Could not verify this email."); setState("error"); });
  }, [searchParams]);
  return <main id="main-content" className="verification-page"><div className="verification-card">{state === "loading" ? <><Loader2 className="verify-icon animate-spin" /><p className="folio">Confirming email</p><h1>Opening your desk…</h1></> : state === "success" ? <><span className="verify-seal"><Check /></span><p className="folio">Email verified</p><h1>You’re all set.</h1><p>You can now go back to the sign-up page. It will show your success state automatically.</p><Link to="/login"><Button>Go to login</Button></Link></> : <><span className="verify-seal error"><X /></span><p className="folio">Link unavailable</p><h1>We couldn’t verify this email.</h1><p>{message}</p><Link to="/signup"><Button>Return to sign up</Button></Link></>}</div></main>;
}
