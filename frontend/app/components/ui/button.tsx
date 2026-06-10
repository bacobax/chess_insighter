import * as React from "react";
import { cn } from "~/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "ghost" | "outline";
  size?: "default" | "sm" | "icon";
};

export function Button({ className, variant = "default", size = "default", style, ...props }: ButtonProps) {
  const variantStyle: React.CSSProperties =
    variant === "default"
      ? { backgroundColor: "var(--accent)", color: "var(--paper)" }
      : variant === "secondary"
      ? { backgroundColor: "var(--paper-dark)", color: "var(--ink)" }
      : variant === "outline"
      ? { backgroundColor: "transparent", color: "var(--ink)", border: "1px solid var(--line)" }
      : { backgroundColor: "transparent", color: "var(--ink)" };

  return (
    <button
      className={cn(
        "inline-flex cursor-pointer items-center justify-center gap-2 rounded text-sm font-medium transition-opacity disabled:pointer-events-none disabled:opacity-40",
        "focus-visible:outline-none focus-visible:ring-2",
        variant === "ghost" && "hover:bg-[rgba(46,42,35,0.07)]",
        variant === "outline" && "hover:bg-[rgba(46,42,35,0.05)]",
        (variant === "default" || variant === "secondary") && "hover:opacity-85",
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
