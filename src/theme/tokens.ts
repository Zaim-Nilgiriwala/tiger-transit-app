/**
 * Design System Tokens - "The Academic Navigator"
 *
 * Color palette rooted in Auburn Navy and Burnt Orange,
 * executed with sophisticated tonal depth.
 *
 * Source: PRD Section 8.2
 */

export const colors = {
  /** Navy - high-authority typography, deep backgrounds */
  primary: '#000D21',
  /** Navy - button fills, navigation elements */
  primaryContainer: '#0C2340',
  /** Burnt Orange - critical action highlights, real-time status */
  secondary: '#994700',
  /** Active bus icons, LIVE badges */
  secondaryContainer: '#FF8934',
  /** Warm accents, capacity bars */
  secondaryFixed: '#FFB68B',
  /** Soft off-white base, reduces eye strain */
  background: '#F8F9FA',
  /** Error states only */
  error: '#BA1A1A',
} as const;

/**
 * Surface Hierarchy (Tonal Layering)
 *
 * Treat the UI as physical layers. No 1px borders --
 * boundaries are defined solely through background color shifts.
 */
export const surfaces = {
  /** Level 0 (Base) - map background, app base */
  level0: '#F8F9FA',
  /** Level 1 (Section) - surface-container - grouped content areas */
  level1: '#EDEEEF',
  /** Level 2 (Cards) - surface-container-lowest - individual interactive elements */
  level2: '#FFFFFF',
  /** Dim - surface-dim - inactive/disabled states */
  dim: '#D9DADB',
} as const;

/**
 * Text Colors
 */
export const textColors = {
  /** Primary text */
  onSurface: '#191C1D',
  /** Secondary text, metadata */
  onSurfaceVariant: '#44474D',
  /** Subtle structural hints */
  outline: '#74777E',
  /** Ghost borders (15% opacity only), grab handle */
  outlineVariant: '#C4C6CE',
} as const;

/**
 * Status Badge Colors
 */
export const statusColors = {
  /** LIVE badge - secondary-fixed orange with pulse animation */
  live: '#FF8934',
  /** DELAYED badge - secondary orange */
  delayed: '#994700',
  /** On Time badge - muted green */
  onTime: '#4CAF50',
  /** On Time badge text */
  onTimeText: '#1B5E20',
} as const;

/**
 * Minimum tap target size per accessibility guidelines (44x44 points)
 */
export const MIN_TAP_TARGET = 44;
