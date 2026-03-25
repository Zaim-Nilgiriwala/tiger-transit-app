/**
 * Shadow Presets - Navy-tinted shadows
 *
 * All shadows use Primary Navy rgba(12, 35, 64, ...), NEVER pure black.
 * This creates a more natural, luminous depth.
 *
 * Source: PRD Section 8.4
 */
import { ViewStyle } from 'react-native';

/**
 * Shadow presets for different elevation contexts.
 *
 * Note: React Native shadows work differently on iOS vs Android.
 * iOS uses shadowColor/shadowOffset/shadowOpacity/shadowRadius.
 * Android uses elevation. Both are included for cross-platform support.
 */
export const shadows = {
  /** Floating elements (FABs, map controls): 0 8px 24px rgba(12, 35, 64, 0.08) */
  ambient: {
    shadowColor: 'rgba(12, 35, 64, 1)',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    elevation: 8,
  } as ViewStyle,

  /** Bottom sheet shadow: 0 -4px 24px rgba(12, 35, 64, 0.08) */
  sheetAbove: {
    shadowColor: 'rgba(12, 35, 64, 1)',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    elevation: 12,
  } as ViewStyle,

  /** Cards - subtle lift: 0 2px 8px rgba(12, 35, 64, 0.04) */
  subtle: {
    shadowColor: 'rgba(12, 35, 64, 1)',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  } as ViewStyle,
} as const;
