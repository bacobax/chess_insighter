import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "~/components/auth/auth-provider";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";

export default function LoginPage() {
  const { user, loading, signIn } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requested = searchParams.get("next");
  const next = requested?.startsWith("/") && !requested.startsWith("//") ? requested : "/dashboard";

  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true });
  }, [loading, navigate, next, user]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signIn(email, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main id="main-content" className="auth-page">
      <section className="auth-editorial" aria-label="Chess Insighter introduction">
        <Link to="/" className="brand-lockup"><span className="brand-mark">♞</span><span><b>Chess Insighter</b><small>Read beyond the move</small></span></Link>
        <div className="auth-quote">
          <p className="folio">Member desk / 01</p>
          <h1>Your private archive of how players think.</h1>
          <p>Build distinct studies, return to earlier snapshots, and keep every opponent dossier in one considered place.</p>
        </div>
        <p className="auth-footnote">Public Chess.com games. Private report library.</p>
      </section>
      <section className="auth-form-panel">
        <div className="auth-form-wrap">
          <p className="folio">Welcome back</p>
          <h2>Sign in to your desk</h2>
          <form onSubmit={submit} className="auth-form">
            <label>Email<Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
            <label>Password<Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <Button type="submit" disabled={submitting}>{submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}Sign in <ArrowRight className="h-4 w-4" /></Button>
          </form>
          <p className="auth-switch">New to Chess Insighter? <Link to="/signup">Create an account</Link></p>
        </div>
      </section>
    </main>
  );
}
