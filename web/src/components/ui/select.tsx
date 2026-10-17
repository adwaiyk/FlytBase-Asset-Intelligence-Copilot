"use client";
import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { CheckIcon, ChevronDownIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const Select = SelectPrimitive.Root;
const SelectValue = SelectPrimitive.Value;
const SelectGroup = SelectPrimitive.Group;

function SelectTrigger({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger data-slot="select-trigger"
      className={cn("border-input flex h-10 w-full items-center justify-between gap-2 rounded-md border bg-background/50 px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/40 focus-visible:ring-[3px] data-[placeholder]:text-muted-foreground [&_svg]:shrink-0", className)} {...props}>
      {children}
      <SelectPrimitive.Icon asChild><ChevronDownIcon className="size-4 opacity-50" /></SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}
function SelectContent({ className, children, position = "popper", ...props }: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content data-slot="select-content" position={position}
        className={cn("bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 relative z-50 max-h-80 min-w-[8rem] overflow-hidden rounded-md border shadow-md",
          position === "popper" && "data-[side=bottom]:translate-y-1 w-full min-w-[var(--radix-select-trigger-width)]", className)} {...props}>
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}
function SelectLabel({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Label>) {
  return <SelectPrimitive.Label className={cn("text-muted-foreground px-2 py-1.5 text-xs uppercase tracking-wider", className)} {...props} />;
}
function SelectItem({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item data-slot="select-item"
      className={cn("focus:bg-accent focus:text-accent-foreground relative flex w-full cursor-default items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50", className)} {...props}>
      <span className="absolute right-2 flex size-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator><CheckIcon className="size-4" /></SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}
export { Select, SelectValue, SelectGroup, SelectTrigger, SelectContent, SelectLabel, SelectItem };
