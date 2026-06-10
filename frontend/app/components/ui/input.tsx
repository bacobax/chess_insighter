import * as React from "react";
import { cn } from "~/lib/utils";

export function Input({ className, style, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-10 w-full rounded px-3 py-2 text-sm outline-none",
        "placeholder:opacity-40 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      style={{
        backgroundColor: "var(--paper)",
        color: "var(--ink)",
        border: "1px solid var(--line)",
        ...style,
      }}
      {...props}
    />
  );
}
