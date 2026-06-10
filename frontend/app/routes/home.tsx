import type { Route } from "./+types/home";
import { UsernameForm } from "~/components/username-form";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Chess Insighter" },
    { name: "description", content: "Chess.com analysis dashboard" },
  ];
}

export default function Home() {
  return <UsernameForm />;
}
