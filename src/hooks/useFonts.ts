/**
 * Font Loading Hook
 *
 * Loads Sweet Sans Pro (Bold, Medium) and Inter (Regular, Medium).
 * Sweet Sans Pro loaded from local assets; Inter from @expo-google-fonts.
 * Font keys match the fontFamily strings used in src/theme/typography.ts.
 */
import { useFonts as useExpoFonts } from 'expo-font';
import {
  Inter_400Regular,
  Inter_500Medium,
} from '@expo-google-fonts/inter';

/**
 * Load all required custom fonts.
 *
 * Font key names MUST match fontFamilies in typography.ts:
 * - SweetSansPro_Bold   -> fontFamilies.headlineBold
 * - SweetSansPro_Medium -> fontFamilies.headlineMedium
 * - Inter_400Regular     -> fontFamilies.interRegular
 * - Inter_500Medium      -> fontFamilies.interMedium
 *
 * @returns { fontsLoaded, fontError }
 */
export function useCustomFonts() {
  const [fontsLoaded, fontError] = useExpoFonts({
    SweetSansPro_Bold: require('../../assets/fonts/SweetSansPro-Bold.otf'),
    SweetSansPro_Medium: require('../../assets/fonts/SweetSansPro-Medium.otf'),
    Inter_400Regular,
    Inter_500Medium,
  });

  return { fontsLoaded, fontError };
}
