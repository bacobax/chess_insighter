import * as React from "react";
import { cn } from "~/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "ghost" | "outline";
  size?: "default" | "sm" | "icon";
};

export function Button({ className, variant = "default", size = "default", style, ...props }: ButtonProps) {
  const variantStyle: React.CSSProperties =
    variant === "default"
      ? { backgroundColor: "var(--ink)", color: "var(--paper-dark)", boxShadow: "0 10px 28px rgba(0,0,0,.18)" }
      : variant === "secondary"
      ? { backgroundColor: "var(--paper-raised)", color: "var(--ink)", border: "1px solid var(--line)" }
      : variant === "outline"
      ? { backgroundColor: "rgba(14,18,16,.64)", color: "var(--ink)", border: "1px solid var(--line)" }
      : { backgroundColor: "transparent", color: "var(--ink)" };

  return (
    <button
      className={cn(
        "inline-flex cursor-pointer items-center justify-center gap-2 rounded-full text-sm font-extrabold transition-all disabled:pointer-events-none disabled:opacity-40",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[#090d0b]",
        variant === "ghost" && "hover:bg-[rgba(33,231,131,0.08)] hover:text-[var(--accent)]",
        variant === "outline" && "hover:-translate-y-0.5 hover:border-[var(--accent)] hover:text-[var(--accent)]",
        (variant === "default" || variant === "secondary") && "hover:-translate-y-0.5 hover:brightness-110",
        size === "default" && "h-10 px-4 py-2",
        size === "sm" && "h-9 px-3",
        size === "icon" && "h-9 w-9",
        className,
      )}
      style={{ ...variantStyle, ...style }}
      {...props}
    />
  );
}
