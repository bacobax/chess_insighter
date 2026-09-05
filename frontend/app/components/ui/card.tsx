import * as React from "react";
import { cn } from "~/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[20px]", className)}
      style={{
        background: "linear-gradient(145deg, var(--paper-raised), var(--paper-dark))",
        border: "1px solid var(--line)",
        boxShadow: "var(--shadow), inset 0 1px 0 rgba(255,255,255,.025)",
      }}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-1.5 p-5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-base font-semibold leading-tight tracking-[-0.02em]", className)}
      style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}
      {...props}
    />
  );
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-sm", className)}
      style={{ color: "var(--ink-soft)" }}
      {...props}
    />
  );
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}
