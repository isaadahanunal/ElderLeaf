// Small line icons (24px grid), drawn inline so there is no icon dependency.
import { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {children}
    </svg>
  );
}

export const IconPlus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
export const IconCamera = (p: P) => (
  <Svg {...p}>
    <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
    <circle cx="12" cy="13" r="3.5" />
  </Svg>
);
export const IconVideo = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="6" width="13" height="12" rx="2" />
    <path d="M16 10l5-3v10l-5-3" />
  </Svg>
);
export const IconUpload = (p: P) => (
  <Svg {...p}>
    <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
  </Svg>
);
export const IconDownload = (p: P) => (
  <Svg {...p}>
    <path d="M12 4v12M7 11l5 5 5-5M4 20h16" />
  </Svg>
);
export const IconDroplet = (p: P) => (
  <Svg {...p}>
    <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />
  </Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}>
    <path d="M12 4l9 16H3z" />
    <path d="M12 10v4M12 17.5v.01" />
  </Svg>
);
export const IconCheck = (p: P) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);
export const IconChevronRight = (p: P) => (
  <Svg {...p}>
    <path d="M9 6l6 6-6 6" />
  </Svg>
);
export const IconNote = (p: P) => (
  <Svg {...p}>
    <path d="M6 3h9l4 4v14H6z" />
    <path d="M14 3v5h5M9 13h7M9 17h5" />
  </Svg>
);
export const IconInfo = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.01" />
  </Svg>
);
export const IconFlag = (p: P) => (
  <Svg {...p}>
    <path d="M5 21V4h11l-2 4 2 4H5" />
  </Svg>
);
export const IconLeaf = (p: P) => (
  <Svg {...p}>
    <path d="M5 19c0-8 5-14 15-15-1 10-7 15-15 15z" />
    <path d="M5 19l7-7" />
  </Svg>
);
export const IconMinus = (p: P) => (
  <Svg {...p}>
    <path d="M6 12h12" />
  </Svg>
);
export const IconSprout = (p: P) => (
  <Svg {...p}>
    <path d="M12 21v-9" />
    <path d="M12 12c0-4 3-7 8-7 0 4-3 7-8 7z" />
    <path d="M12 14c0-3-2.5-5.5-7-5.5 0 3 2.5 5.5 7 5.5z" />
  </Svg>
);
export const IconCover = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 3.5v8.5h8.5" />
  </Svg>
);
export const IconGrass = (p: P) => (
  <Svg {...p}>
    <path d="M4 20c1-5 0-9-2-12M9 20c0-6 1-10 4-14M14 20c0-4 1-7 4-9M19 20c0-3 1-5 3-6" />
  </Svg>
);
export const IconHeart = (p: P) => (
  <Svg {...p}>
    <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />
    <path d="M7.5 12h2.5l1.2-2 1.6 4 1.2-2h2.5" />
  </Svg>
);
export const IconRuler = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="8" width="18" height="8" rx="1.5" />
    <path d="M7 8v3M11 8v4M15 8v3M19 8v2" />
  </Svg>
);
export const IconSpots = (p: P) => (
  <Svg {...p}>
    <circle cx="8" cy="9" r="2" />
    <circle cx="15.5" cy="7.5" r="1.5" />
    <circle cx="14" cy="15" r="2.5" />
    <circle cx="7" cy="16" r="1" />
  </Svg>
);
export const IconSparkle = (p: P) => (
  <Svg {...p}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
  </Svg>
);
export const IconGrid = (p: P) => (
  <Svg {...p}>
    <rect x="4" y="4" width="7" height="7" rx="1.5" />
    <rect x="13" y="4" width="7" height="7" rx="1.5" />
    <rect x="4" y="13" width="7" height="7" rx="1.5" />
    <rect x="13" y="13" width="7" height="7" rx="1.5" />
  </Svg>
);
export const IconBook = (p: P) => (
  <Svg {...p}>
    <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" />
    <path d="M4 19V5M9 7h6" />
  </Svg>
);
export const IconCalendar = (p: P) => (
  <Svg {...p}>
    <rect x="4" y="5" width="16" height="15" rx="2" />
    <path d="M4 10h16M9 3v4M15 3v4" />
  </Svg>
);
export const IconPin = (p: P) => (
  <Svg {...p}>
    <path d="M12 21s-6-5.4-6-11a6 6 0 0 1 12 0c0 5.6-6 11-6 11z" />
    <circle cx="12" cy="10" r="2.2" />
  </Svg>
);
export const IconEye = (p: P) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </Svg>
);
export const IconSteps = (p: P) => (
  <Svg {...p}>
    <circle cx="6" cy="6" r="2" />
    <circle cx="18" cy="12" r="2" />
    <circle cx="6" cy="18" r="2" />
    <path d="M8 6h4a4 4 0 0 1 4 4M16 14a4 4 0 0 1-4 4H8" />
  </Svg>
);
export const IconArrowUp = (p: P) => (
  <Svg {...p}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Svg>
);
export const IconArrowDown = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M6 13l6 6 6-6" />
  </Svg>
);
export const IconHome = (p: P) => (
  <Svg {...p}>
    <path d="M4 11l8-7 8 7v9h-5v-6H9v6H4z" />
  </Svg>
);
export const IconClose = (p: P) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);
export const IconServer = (p: P) => (
  <Svg {...p}>
    <rect x="4" y="4" width="16" height="7" rx="2" />
    <rect x="4" y="13" width="16" height="7" rx="2" />
    <path d="M8 7.5h.01M8 16.5h.01" />
  </Svg>
);
export const IconImage = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="9" cy="10" r="2" />
    <path d="M21 16l-5-5-9 9" />
  </Svg>
);
export const IconUser = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 20c1.5-3.6 4.5-5.4 8-5.4s6.5 1.8 8 5.4" />
  </Svg>
);
export const IconLogout = (p: P) => (
  <Svg {...p}>
    <path d="M10 5H5v14h5M14 8l4 4-4 4M18 12H9" />
  </Svg>
);
export const IconEyeOff = (p: P) => (
  <Svg {...p}>
    <path d="M3 3l18 18M10.6 6.2A9.8 9.8 0 0 1 12 6c5 0 8.5 4.5 9.5 6-.5.8-1.6 2.2-3.1 3.5M6.3 7.8C4.5 9.1 3.2 10.9 2.5 12c1 1.5 4.5 6 9.5 6 1.3 0 2.5-.3 3.6-.8M9.9 9.9a3 3 0 0 0 4.2 4.2" />
  </Svg>
);
export const IconSun = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4" />
  </Svg>
);
export const IconSettings = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Svg>
);
