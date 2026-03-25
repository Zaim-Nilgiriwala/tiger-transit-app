/**
 * Glassmorphism Presets
 *
 * For floating elements (bottom sheet, map overlays, callout bubbles):
 * - backdrop-filter: blur(20px)
 * - Surface color at specified opacity
 * - Navy-tinted shadow underneath
 * - No opaque backgrounds on floating elements
 *
 * Source: PRD Section 8.7
 */
import { ViewStyle } from 'react-native';
import { surfaces } from './tokens';

/**
 * Glass style preset parameters.
 *
 * backdropBlur: intensity for expo-blur BlurView
 * opacity: background opacity (0-1)
 * borderRadius values for the container shape
 */
export const glass = {
  /** Glass panel - floating map controls, callout bubbles */
  panel: {
    backdropBlur: 20,
    opacity: 0.95,
    borderRadius: 8,
  },

  /** Bottom sheet - main navigation surface */
  sheet: {
    backdropBlur: 20,
    opacity: 0.85,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },

  /** Callout bubble - stop and bus callouts */
  callout: {
    backdropBlur: 20,
    opacity: 0.95,
    borderRadius: 8,
  },
} as const;

/**
 * Create a ViewStyle for a glass-panel container.
 *
 * Use this with expo-blur's BlurView for the actual backdrop blur,
 * or as a fallback style for platforms without blur support.
 *
 * @param preset - One of the glass preset keys
 * @returns ViewStyle with backgroundColor at the given opacity and border radius
 */
export function createGlassStyle(
  preset: keyof typeof glass
): ViewStyle {
  const config = glass[preset];

  // Convert surfaces.level2 (#FFFFFF) to rgba with the preset opacity
  const alpha = Math.round(config.opacity * 255)
    .toString(16)
    .padStart(2, '0');
  const backgroundColor = `${surfaces.level2}${alpha}`;

  const style: ViewStyle = {
    backgroundColor,
    overflow: 'hidden',
  };

  if ('borderRadius' in config) {
    style.borderRadius = config.borderRadius;
  }
  if ('borderTopLeftRadius' in config) {
    style.borderTopLeftRadius = config.borderTopLeftRadius;
    style.borderTopRightRadius = config.borderTopRightRadius;
  }

  return style;
}
