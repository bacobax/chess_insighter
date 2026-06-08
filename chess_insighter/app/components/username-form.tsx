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
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-950">
      <section className="mx-auto flex min-h-[80vh] max-w-2xl items-center">
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-2xl">Chess Insighter</CardTitle>
            <CardDescription>Enter a Chess.com username to browse games and build a player report.</CardDescription>
          </CardHeader>
          <CardContent>
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
            {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
