import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "~/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex h-10 items-center rounded-full border p-1", className)}
      style={{ backgroundColor: "var(--paper-dark)", borderColor: "var(--line)" }}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "rounded-full px-3 py-1.5 text-sm font-semibold transition-colors",
        "data-[state=active]:bg-[var(--acid)] data-[state=active]:text-[#0a0e0b]! data-[state=active]:shadow-sm",
        className,
      )}
      style={{ color: "var(--ink-soft)" }}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: TabsPrimitive.TabsContentProps) {
  return <TabsPrimitive.Content className={cn("mt-4", className)} {...props} />;
}
