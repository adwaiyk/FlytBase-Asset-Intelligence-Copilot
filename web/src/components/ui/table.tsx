import * as React from "react";
import { cn } from "@/lib/utils";

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return <div className="relative w-full overflow-auto"><table className={cn("w-full caption-bottom text-sm", className)} {...props} /></div>;
}
function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("[&_tr]:border-b sticky top-0 bg-card z-10", className)} {...props} />;
}
function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}
function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return <tr className={cn("hover:bg-muted/40 border-b transition-colors", className)} {...props} />;
}
function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return <th className={cn("text-muted-foreground h-9 px-2.5 text-left align-middle text-xs font-medium uppercase tracking-wide whitespace-nowrap", className)} {...props} />;
}
function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-2.5 py-2 align-top", className)} {...props} />;
}
export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
