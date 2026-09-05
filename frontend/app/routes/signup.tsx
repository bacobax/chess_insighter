import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { Check, Loader2, Mail, RotateCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { register, registrationSocketUrl, resendVerification } from "~/lib/api";
import type { RegisterResponse } from "~/lib/types";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [registration, setRegistration] = useState<RegisterResponse | null>(null);
  const [verified, setVerified] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(60);
  const retries = useRef(0);

  useEffect(() => {
    if (!registration || verified) return;
    let socket: WebSocket | null = null;
    let reconnect: number | undefined;
    let closed = false;
    const connect = () => {
      socket = new WebSocket(registrationSocketUrl(registration.registration_id, registration.socket_token));
      socket.onmessage = (event) => {
        const payload = JSON.parse(String(event.data)) as { status: string };
        if (payload.status === "verified") setVerified(true);
        if (payload.status === "expired" || payload.status === "invalid") setError("This registration has expired. Start again.");
      };
      socket.onopen = () => { retries.current = 0; };
      socket.onclose = () => {
        if (!closed && !verified && retries.current < 6) {
          reconnect = window.setTimeout(connect, Math.min(1000 * 2 ** retries.current++, 10000));
        }
      };
    };
    connect();
    return () => { closed = true; socket?.close(); if (reconnect) window.clearTimeout(reconnect); };
  }, [registration, verified]);

  useEffect(() => {
    if (!registration || cooldown <= 0) return;
    const timer = window.setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [cooldown, registration]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmation) { setError("Passwords do not match."); return; }
    setSubmitting(true); setError(null);
    try {
      setRegistration(await register(email, password));
      setCooldown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create your account.");
    } finally { setSubmitting(false); }
  }

  async function resend() {
    if (!registration) return;
    setError(null);
    try {
      await resendVerification(registration.registration_id, registration.socket_token);
      setCooldown(60);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not resend the email."); }
  }

  return (
    <main id="main-content" className="auth-page">
      <section className="auth-editorial">
        <Link to="/" className="brand-lockup"><span className="brand-mark">♞</span><span><b>Chess Insighter</b><small>Private analysis desk</small></span></Link>
        <div className="auth-quote"><p className="folio">Membership / 02</p><h1>Keep every player study in your own archive.</h1><p>One account, any number of players, and as many reports as your preparation demands.</p></div>
      </section>
      <section className="auth-form-panel">
        <div className="auth-form-wrap">
          {verified ? (
            <div className="verification-success" aria-live="polite"><span><Check /></span><p className="folio">Email confirmed</p><h2>Your desk is ready.</h2><p>The sign-up page received your confirmation. You can sign in now.</p><Link to="/login"><Button>Go to login</Button></Link></div>
          ) : registration ? (
            <div className="verification-wait" aria-live="polite"><span className="mail-seal"><Mail /></span><p className="folio">Check your inbox</p><h2>Confirm {email}</h2><p>Keep this page open. It will update automatically as soon as you use the verification link.</p><div className="socket-status"><span /> Waiting for confirmation</div>{error ? <p className="form-error" role="alert">{error}</p> : null}<Button variant="outline" disabled={cooldown > 0} onClick={() => void resend()}><RotateCw className="h-4 w-4" />{cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}</Button></div>
          ) : (
            <><p className="folio">Create account</p><h2>Open your analysis desk</h2><form onSubmit={submit} className="auth-form"><label>Email<Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label><label>Password <small>12 characters minimum</small><Input type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label><label>Confirm password<Input type="password" minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" required /></label>{error ? <p className="form-error" role="alert">{error}</p> : null}<Button type="submit" disabled={submitting}>{submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}Send verification email</Button></form><p className="auth-switch">Already a member? <Link to="/login">Sign in</Link></p></>
          )}
        </div>
      </section>
    </main>
  );
}
