export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
        <defs>
          <linearGradient id="titanG" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#2DE1C2" />
            <stop offset="1" stopColor="#6E5BFF" />
          </linearGradient>
        </defs>
        <rect x="2" y="2" width="28" height="28" rx="7" fill="url(#titanG)" opacity="0.18" />
        <path
          d="M8 11h16M16 11v13M11 19l5 5 5-5"
          stroke="url(#titanG)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="16" cy="11" r="2.5" fill="url(#titanG)" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-white">
        TITAN
      </span>
    </div>
  );
}
