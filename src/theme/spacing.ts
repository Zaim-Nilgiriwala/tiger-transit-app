/**
 * Spacing & Layout - 8px grid system
 *
 * Source: PRD Section 8.6
 */

/** Base grid unit (8px) */
export const GRID = 8;

/** Minimum screen-edge margins (20px) */
export const EDGE_MARGIN = 20;

/**
 * Spacing scale based on 8px grid
 */
export const spacing = {
  /** 8px */
  s1: GRID * 1,
  /** 16px */
  s2: GRID * 2,
  /** 24px */
  s3: GRID * 3,
  /** 32px */
  s4: GRID * 4,
  /** 40px */
  s5: GRID * 5,
  /** 48px */
  s6: GRID * 6,
  /** 64px */
  s8: GRID * 8,
  /** 96px */
  s12: GRID * 12,
} as const;

/** Card internal padding (16px) */
export const cardPadding = spacing.s2;

/** Vertical white space between list items (16px) */
export const listItemGap = spacing.s2;

/** Card border radius (8px - round-eight per PRD) */
export const cardRadius = GRID;

/** Pill shape border radius for toggles and badges */
export const pillRadius = 999;
