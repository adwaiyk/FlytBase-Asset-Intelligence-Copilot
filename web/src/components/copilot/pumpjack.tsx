export function PumpJack({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 80" className={className} aria-hidden="true">
      <rect x="6" y="72" width="88" height="4" rx="2" className="fill-primary/40" />
      <path d="M44 72 L50 30 L56 72 Z" className="fill-none stroke-primary" strokeWidth="3" strokeLinejoin="round" />
      <g className="pump-beam">
        <rect x="14" y="26" width="72" height="7" rx="3" className="fill-primary" />
        <path d="M80 20 q12 9 0 20 z" className="fill-primary" />
        <circle cx="50" cy="30" r="3.5" className="fill-background stroke-primary" strokeWidth="2" />
      </g>
      <g className="pump-rod"><line x1="88" y1="36" x2="88" y2="72" className="stroke-primary/80" strokeWidth="2" /></g>
      <rect x="10" y="56" width="16" height="16" rx="2" className="fill-primary/25 stroke-primary/60" strokeWidth="1.5" />
    </svg>
  );
}
