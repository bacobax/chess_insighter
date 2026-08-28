import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import { ArrowUpRight, Search, Sparkles } from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { SavedReportsList } from "./saved-reports-list";

export function UsernameForm() {
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = username.trim();
    if (!value) {
      setError("Enter a Chess.com username.");
      return;
    }
    navigate(`/games/${encodeURIComponent(value)}`);
  }

  return (
    <main id="main-content" className="page-shell min-h-screen overflow-hidden px-5 py-6 sm:px-8 lg:px-12" style={{ color: "var(--ink)" }}>
      <nav className="mx-auto flex max-w-7xl items-center justify-between" aria-label="Primary navigation">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl border border-[var(--accent)] bg-[var(--accent)] text-2xl font-black text-[#09100c] shadow-[0_0_28px_var(--glow)]">♞</div>
          <div>
            <div className="font-[var(--font-display)] text-sm font-bold tracking-[-0.03em]">CHESS INSIGHTER</div>
            <div className="text-[9px] font-bold uppercase tracking-[.28em] text-[var(--ink-faint)]">Read beyond the move</div>
          </div>
        </div>
        <div className="hidden items-center gap-2 rounded-full border border-[var(--line)] bg-[rgba(13,19,16,.72)] px-4 py-2 text-xs font-semibold text-[var(--ink-soft)] backdrop-blur sm:flex">
          <span className="h-2 w-2 rounded-full bg-[var(--accent)] shadow-[0_0_12px_var(--accent)]" /> Chess.com analysis online
        </div>
      </nav>

      <div className="mx-auto grid min-h-[calc(100vh-7rem)] max-w-7xl items-center gap-12 py-12 lg:grid-cols-[1.05fr_.95fr] lg:py-16">
        <section className="relative">
          <p className="eyebrow mb-5 flex items-center gap-2"><Sparkles className="h-3.5 w-3.5" /> Player intelligence / 01</p>
          <h1 className="display-title max-w-[10ch]">SEE THE<br /><span className="text-[var(--accent)]">WHOLE</span> BOARD.</h1>
          <p className="mt-7 max-w-xl text-base leading-7 text-[var(--ink-soft)] sm:text-lg">
            Turn match history into a living profile of your decisions, openings, blind spots, and best next move.
          </p>
          <div className="mt-9 grid max-w-lg grid-cols-3 gap-2 text-center">
            {[["01", "Scan games"], ["02", "Map style"], ["03", "Study smarter"]].map(([n, label]) => (
              <div key={n} className="rounded-2xl border border-[var(--line)] bg-[rgba(21,28,24,.64)] px-3 py-4 backdrop-blur">
                <div className="text-xs font-extrabold text-[var(--acid)]">{n}</div>
                <div className="mt-1 text-[11px] font-semibold text-[var(--ink-soft)] sm:text-xs">{label}</div>
              </div>
            ))}
          </div>
          <div className="pointer-events-none absolute -bottom-20 -left-12 -z-10 text-[19rem] leading-none text-[rgba(33,231,131,.035)]" aria-hidden="true">♜</div>
        </section>

        <section className="relative">
          <div className="absolute -inset-4 -z-10 rotate-2 rounded-[32px] border border-[rgba(33,231,131,.18)] bg-[rgba(33,231,131,.025)]" />
          <Card className="w-full overflow-hidden">
            <CardHeader className="border-b border-[var(--line-faint)] p-6 sm:p-8">
              <div className="mb-5 flex items-center justify-between">
                <span className="eyebrow">Start analysis</span>
                <span className="font-[var(--font-display)] text-4xl text-[var(--accent)]">♙</span>
              </div>
              <CardTitle className="text-3xl sm:text-4xl">Who are we studying?</CardTitle>
              <CardDescription className="mt-2 max-w-md leading-6">Enter a Chess.com handle. We’ll load recent games first, then you can build the deeper report.</CardDescription>
            </CardHeader>
            <CardContent className="p-6 sm:p-8">
              <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ink-faint)]" />
                  <Input className="pl-11" value={username} onChange={(event) => { setUsername(event.target.value); setError(null); }} placeholder="Chess.com username" aria-label="Chess.com username" autoComplete="username" />
                </div>
                <Button type="submit" className="h-11 px-5">Analyze <ArrowUpRight className="h-4 w-4" /></Button>
              </form>
              {error ? <p className="mt-3 text-sm text-[#ff947f]" role="alert">{error}</p> : null}
              <p className="mt-5 text-[11px] leading-5 text-[var(--ink-faint)]">No sign-in required · Public games only · Saved locally</p>
            </CardContent>
          </Card>
        </section>
      </div>

      <section className="mx-auto max-w-7xl pb-16" aria-label="Saved analysis reports">
        <SavedReportsList />
      </section>
    </main>
  );
}
