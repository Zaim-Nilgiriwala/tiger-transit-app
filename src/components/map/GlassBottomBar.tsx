/**
 * GlassBottomBar - Static glassmorphic bottom bar
 *
 * Fixed at the bottom of the screen (~80px height).
 * Contains a grab handle pill, search placeholder, and settings icon.
 * Built as a self-contained component so Phase 3 can wrap it with
 * drag/snap behavior without rewriting.
 *
 * Design system compliance:
 * - DS-01: Tonal layering (level2 bar on level0 map, level1 search inside bar)
 * - DS-02/DS-03: Search placeholder uses Inter (bodyMD)
 * - DS-04: Navy-tinted shadow above (sheetAbove)
 * - DS-05: 20px edge margins, 8px grid spacing
 * - DS-07: All tappable elements >= 44x44pt (search 40h+hitSlop, settings 40+hitSlop)
 * - DS-08: Placeholder text #44474D on #EDEEEF = ~4.7:1 contrast (WCAG AA)
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { MaterialIcons } from '@expo/vector-icons';

import {
  surfaces,
  textColors,
  shadows,
  typography,
  spacing,
  EDGE_MARGIN,
} from '../../theme';
import { showToast } from '../../utils/toast';

/** Bar height visible at bottom of screen */
const BAR_HEIGHT = 80;

/** Grab handle dimensions */
const HANDLE_WIDTH = 32;
const HANDLE_HEIGHT = 4;

/** Search bar height */
const SEARCH_HEIGHT = 40;

/** Settings button size */
const SETTINGS_SIZE = 40;

export default function GlassBottomBar() {
  return (
    <View style={styles.container}>
      <BlurView intensity={20} tint="light" style={styles.blur}>
        <View style={styles.content}>
          {/* Grab handle pill */}
          <View style={styles.handleRow}>
            <View style={styles.handle} />
          </View>

          {/* Search + Settings row */}
          <View style={styles.controlsRow}>
            {/* Search bar placeholder */}
            <Pressable
              style={styles.searchBar}
              onPress={() => showToast('Coming soon')}
              accessibilityLabel="Search routes or stops"
              accessibilityRole="button"
              hitSlop={{ top: 4, bottom: 4 }}
            >
              <MaterialIcons
                name="search"
                size={20}
                color={textColors.onSurfaceVariant}
              />
              <Text style={styles.searchPlaceholder}>
                Search routes or stops
              </Text>
            </Pressable>

            {/* Settings icon button */}
            <Pressable
              style={({ pressed }) => [
                styles.settingsButton,
                pressed && styles.settingsPressed,
              ]}
              onPress={() => showToast('Coming soon')}
              accessibilityLabel="Settings"
              accessibilityRole="button"
              hitSlop={{ top: 4, bottom: 4, left: 4, right: 4 }}
            >
              <MaterialIcons
                name="settings"
                size={24}
                color={textColors.onSurface}
              />
            </Pressable>
          </View>
        </View>
      </BlurView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: BAR_HEIGHT,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    overflow: 'hidden',
    ...shadows.sheetAbove,
  },
  blur: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.85)',
  },
  content: {
    flex: 1,
  },
  handleRow: {
    alignItems: 'center',
    marginTop: spacing.s1,
  },
  handle: {
    width: HANDLE_WIDTH,
    height: HANDLE_HEIGHT,
    borderRadius: HANDLE_HEIGHT / 2,
    backgroundColor: textColors.outlineVariant,
  },
  controlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: EDGE_MARGIN,
    marginTop: spacing.s1,
  },
  searchBar: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    height: SEARCH_HEIGHT,
    backgroundColor: surfaces.level1,
    borderRadius: spacing.s1,
    paddingHorizontal: 12,
  },
  searchPlaceholder: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    marginLeft: spacing.s1,
  },
  settingsButton: {
    width: SETTINGS_SIZE,
    height: SETTINGS_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: spacing.s1,
  },
  settingsPressed: {
    opacity: 0.6,
  },
});
