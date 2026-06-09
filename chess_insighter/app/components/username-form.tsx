import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import { Search } from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

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
    <main className="min-h-screen px-4 py-10" style={{ color: "var(--ink)" }}>
      <section className="mx-auto flex min-h-[80vh] max-w-lg items-center">
        <Card className="w-full">
          <CardHeader className="pb-3">
            <div className="mb-2 text-center text-sm tracking-widest uppercase" style={{ color: "var(--ink-faint)", letterSpacing: "0.2em" }}>
              ♔ Analysis &amp; Insight ♔
            </div>
            <CardTitle className="text-center" style={{ fontFamily: "var(--font-display)", fontSize: "2rem", lineHeight: 1.1 }}>
              Chess Insighter
            </CardTitle>
            <div className="mt-1 flex justify-center">
              <div className="h-px w-24" style={{ backgroundColor: "var(--line)" }} />
            </div>
          </CardHeader>
          <CardContent>
            <CardDescription className="mb-4 text-center text-sm">
              Enter a Chess.com username to browse games and build a player report.
            </CardDescription>
            <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
              <Input
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value);
                  setError(null);
                }}
                placeholder="Chess.com username"
                aria-label="Chess.com username"
              />
              <Button type="submit">
                <Search className="h-4 w-4" />
                Continue
              </Button>
            </form>
            {error ? <p className="mt-3 text-sm" style={{ color: "var(--accent)" }}>{error}</p> : null}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
