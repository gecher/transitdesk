import { linkProps } from "../router";

export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
      <rect x="1" y="1" width="32" height="32" rx="5" fill="#10233f" />
      <path d="M8 23h18M10 23V13l7-4 7 4v10M14 23v-5h6v5" fill="none" stroke="#f5c518" strokeWidth="2.4" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand({ subtitle }: { subtitle: string }) {
  return (
    <a className="brand" {...linkProps("/")} aria-label="TransitDesk home">
      <Logo />
      <div>
        <span className="brand-name">TransitDesk</span>
        <span className="brand-sub">{subtitle}</span>
      </div>
    </a>
  );
}

export const GITHUB_REPO = "https://github.com/gecher/transitdesk";
export const GITHUB_PROFILE = "https://github.com/gecher";
