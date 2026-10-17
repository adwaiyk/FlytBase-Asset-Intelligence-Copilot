import * as React from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn("placeholder:text-muted-foreground border-input flex w-full rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-0 disabled:opacity-50", className)} {...props} />;
}
export { Textarea };
