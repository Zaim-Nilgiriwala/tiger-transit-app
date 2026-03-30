/**
 * Typography - Dual-font strategy
 *
 * Sweet Sans Pro (Bold, Medium): Display & headlines, route names, screen titles
 * Inter (Regular, Medium): Body & labels, timestamps, stop names, metadata
 *
 * Source: PRD Section 8.3
 */
import { TextStyle } from 'react-native';

/**
 * Font family names - must exactly match the keys used in useFonts hook
 */
export const fontFamilies = {
  headlineBold: 'SweetSansPro_Bold',
  headlineMedium: 'SweetSansPro_Medium',
  interRegular: 'Inter_400Regular',
  interMedium: 'Inter_500Medium',
} as const;

/**
 * Type scale - StyleSheet-compatible text style objects
 *
 * | Style       | Size | Weight              | Usage                                    |
 * |-------------|------|---------------------|------------------------------------------|
 * | headlineLG  | 32pt | Sweet Sans Pro Bold | Primary screen titles, ETA large numbers |
 * | titleMD     | 18pt | Sweet Sans Pro Med  | Card headings, section titles            |
 * | bodyMD      | 14pt | Inter Regular       | Descriptions, secondary content          |
 * | labelSM     | 11pt | Inter Medium        | Metadata: "BUS ID", stop numbers         |
 */
export const typography = {
  headlineLG: {
    fontFamily: fontFamilies.headlineBold,
    fontSize: 32,
    lineHeight: 40,
  } as TextStyle,

  titleMD: {
    fontFamily: fontFamilies.headlineMedium,
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
