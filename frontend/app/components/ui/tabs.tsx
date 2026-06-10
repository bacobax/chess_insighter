import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "~/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex h-9 items-center rounded p-1", className)}
      style={{ backgroundColor: "var(--line-faint)" }}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "rounded px-3 py-1 text-sm transition-colors",
        "data-[state=active]:bg-[var(--paper)] data-[state=active]:shadow-sm data-[state=active]:font-medium",
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
