import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowUpRight, LogOut, Search } from "lucide-react";
import { RequireAuth, useAuth } from "~/components/auth/auth-provider";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");

  function search(event: FormEvent) {
    event.preventDefault();
    const value = username.trim();
    if (value) navigate(`/report/${encodeURIComponent(value)}`);
  }

  return (
    <RequireAuth>
      <div className="min-h-screen">
        <header className="app-header">
          <Link to="/dashboard" className="brand-lockup" aria-label="Chess Insighter dashboard">
            <span className="brand-mark">♞</span>
            <span><b>Chess Insighter</b><small>Private analysis desk</small></span>
          </Link>
          <form onSubmit={search} className="header-search">
            <Search aria-hidden="true" />
            <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Open a Chess.com player" aria-label="Chess.com username" />
            <button type="submit" aria-label="Open player"><ArrowUpRight /></button>
          </form>
          <div className="account-cluster">
            <span className="account-email">{user?.email}</span>
            <Button variant="ghost" size="sm" onClick={() => void signOut()} aria-label="Sign out">
              <LogOut className="h-4 w-4" /> <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </header>
        {children}
      </div>
    </RequireAuth>
  );
}
