/**
 * Typography - Dual-font strategy
 *
 * Manrope (Bold, Medium): Display & headlines, route names, screen titles
 * Inter (Regular, Medium): Body & labels, timestamps, stop names, metadata
 *
 * Source: PRD Section 8.3
 */
import { TextStyle } from 'react-native';

/**
 * Font family names - must exactly match the keys used in useFonts hook
 */
export const fontFamilies = {
  manropeBold: 'Manrope_700Bold',
  manropeMedium: 'Manrope_500Medium',
  interRegular: 'Inter_400Regular',
  interMedium: 'Inter_500Medium',
} as const;

/**
 * Type scale - StyleSheet-compatible text style objects
 *
 * | Style       | Size | Weight         | Usage                                    |
 * |-------------|------|----------------|------------------------------------------|
 * | headlineLG  | 32pt | Manrope Bold   | Primary screen titles, ETA large numbers |
 * | titleMD     | 18pt | Manrope Medium | Card headings, section titles            |
 * | bodyMD      | 14pt | Inter Regular  | Descriptions, secondary content          |
 * | labelSM     | 11pt | Inter Medium   | Metadata: "BUS ID", stop numbers         |
 */
export const typography = {
  headlineLG: {
    fontFamily: fontFamilies.manropeBold,
    fontSize: 32,
    lineHeight: 40,
  } as TextStyle,

  titleMD: {
    fontFamily: fontFamilies.manropeMedium,
    fontSize: 18,
    lineHeight: 24,
  } as TextStyle,

  bodyMD: {
    fontFamily: fontFamilies.interRegular,
    fontSize: 14,
    lineHeight: 20,
  } as TextStyle,

  labelSM: {
    fontFamily: fontFamilies.interMedium,
    fontSize: 11,
    lineHeight: 16,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.55,
  } as TextStyle,
} as const;
