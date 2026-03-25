/**
 * Font Loading Hook
 *
 * Loads Manrope (Bold, Medium) and Inter (Regular, Medium) from
 * @expo-google-fonts packages. Font keys match the fontFamily
 * strings used in src/theme/typography.ts.
 */
import { useFonts as useExpoFonts } from 'expo-font';
import {
  Manrope_500Medium,
  Manrope_700Bold,
} from '@expo-google-fonts/manrope';
import {
  Inter_400Regular,
  Inter_500Medium,
} from '@expo-google-fonts/inter';

/**
 * Load all required custom fonts.
 *
 * Font key names MUST match fontFamilies in typography.ts:
 * - Manrope_700Bold  -> fontFamilies.manropeBold
 * - Manrope_500Medium -> fontFamilies.manropeMedium
 * - Inter_400Regular  -> fontFamilies.interRegular
 * - Inter_500Medium   -> fontFamilies.interMedium
 *
 * @returns { fontsLoaded, fontError }
 */
export function useCustomFonts() {
  const [fontsLoaded, fontError] = useExpoFonts({
    Manrope_700Bold,
    Manrope_500Medium,
    Inter_400Regular,
    Inter_500Medium,
  });

  return { fontsLoaded, fontError };
}
