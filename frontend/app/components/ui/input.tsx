import * as React from "react";
import { cn } from "~/lib/utils";

export function Input({ className, style, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-11 w-full rounded-full px-4 py-2 text-sm outline-none transition-all",
        "placeholder:opacity-45 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--glow)] disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      style={{
        backgroundColor: "var(--paper-dark)",
        color: "var(--ink)",
        border: "1px solid var(--line)",
        ...style,
      }}
      {...props}
    />
  );
}
