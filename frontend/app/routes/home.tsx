import type { Route } from "./+types/home";
import { Navigate } from "react-router";
import { useAuth } from "~/components/auth/auth-provider";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Chess Insighter" },
    { name: "description", content: "Chess.com analysis dashboard" },
  ];
}

export default function Home() {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center text-sm text-[var(--ink-soft)]">Opening Chess Insighter…</div>;
  return <Navigate to={user ? "/dashboard" : "/login"} replace />;
}
