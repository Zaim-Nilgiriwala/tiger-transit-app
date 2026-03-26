/**
 * BottomSheet - Draggable glassmorphic bottom sheet
 *
 * Three snap points (collapsed, half, full) with spring animation.
 * Uses react-native-gesture-handler for pan gestures and
 * react-native-reanimated for smooth spring-driven transforms.
 *
 * Design system compliance:
 * - SHEET-01: Three discrete snap points at ~80px, ~45%, ~90%
 * - SHEET-02: Glassmorphism via BlurView + rgba background + navy shadow
 * - SHEET-03: #C4C6CE grab handle pill, 32x4, centered at top
 * - SHEET-04: Spring animation between snap points
 * - SHEET-05: Map remains interactive above the sheet
 * - ERR-03: Loading spinner when route data is loading
 *
 * The sheet is absolutely positioned and only captures gestures
 * within its own bounds, so the map behind receives touches on
 * uncovered areas naturally.
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  runOnJS,
  useAnimatedScrollHandler,
  useDerivedValue,
  useAnimatedRef,
} from 'react-native-reanimated';
import { BlurView } from 'expo-blur';
import { MaterialIcons } from '@expo/vector-icons';

import {
  textColors,
  shadows,
  typography,
  spacing,
  surfaces,
  EDGE_MARGIN,
} from '../../theme';
import { useAppDispatch } from '../../store';
import { setSheetPosition } from '../../store/slices/uiSlice';
import { showToast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Bar height in collapsed state */
const COLLAPSED_HEIGHT = 80;

/** Grab handle dimensions */
const HANDLE_WIDTH = 32;
const HANDLE_HEIGHT = 4;

/** Search bar height */
const SEARCH_HEIGHT = 40;

/** Settings button size */
const SETTINGS_SIZE = 40;

/** Spring config for snap animation */
const SPRING_CONFIG = {
  damping: 20,
  stiffness: 150,
  mass: 1,
  overshootClamping: false,
  restDisplacementThreshold: 0.5,
  restSpeedThreshold: 0.5,
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BottomSheetProps {
  children?: React.ReactNode;
  loading?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BottomSheet({ children, loading = false }: BottomSheetProps) {
  const { height: screenHeight } = useWindowDimensions();
  const dispatch = useAppDispatch();
  const scrollRef = useAnimatedRef<Animated.ScrollView>();
  const [canScroll, setCanScroll] = useState(false);

  // -------------------------------------------------------------------------
  // Snap points (translateY values — 0 is top of screen)
  // -------------------------------------------------------------------------
  const collapsedY = screenHeight - COLLAPSED_HEIGHT;
  const halfY = screenHeight * 0.55;
  const fullY = screenHeight * 0.10;

  // -------------------------------------------------------------------------
  // Shared values
  // -------------------------------------------------------------------------
  const translateY = useSharedValue(collapsedY);
  const context = useSharedValue(0);
  const scrollOffset = useSharedValue(0);

  // Whether scroll is enabled (only at full position)
  const isAtFull = useDerivedValue(() => {
    return Math.abs(translateY.value - fullY) < 5;
  });

  // -------------------------------------------------------------------------
  // Redux sync helper (called via runOnJS)
  // -------------------------------------------------------------------------
  const syncSheetPosition = (position: 'collapsed' | 'half' | 'full') => {
    dispatch(setSheetPosition(position));
    setCanScroll(position === 'full');
  };

  // -------------------------------------------------------------------------
  // Find nearest snap point
  // -------------------------------------------------------------------------
  const snapToNearest = (currentY: number, velocityY: number) => {
    'worklet';
    const snapPoints = [fullY, halfY, collapsedY];
    const labels: Array<'full' | 'half' | 'collapsed'> = ['full', 'half', 'collapsed'];

    // Factor in velocity — flinging toward a snap point biases selection
    const projected = currentY + velocityY * 0.15;

    let closestIndex = 0;
    let closestDistance = Math.abs(projected - snapPoints[0]);

    for (let i = 1; i < snapPoints.length; i++) {
      const distance = Math.abs(projected - snapPoints[i]);
      if (distance < closestDistance) {
        closestDistance = distance;
        closestIndex = i;
      }
    }

    translateY.value = withSpring(snapPoints[closestIndex], SPRING_CONFIG, (finished) => {
      if (finished) {
        runOnJS(syncSheetPosition)(labels[closestIndex]);
      }
    });
  };

  // -------------------------------------------------------------------------
  // Scroll handler for the inner ScrollView
  // -------------------------------------------------------------------------
  const scrollHandler = useAnimatedScrollHandler({
    onScroll: (event) => {
      scrollOffset.value = event.contentOffset.y;
    },
  });

  // -------------------------------------------------------------------------
  // Pan gesture
  // -------------------------------------------------------------------------
  const panGesture = Gesture.Pan()
    .onStart(() => {
      context.value = translateY.value;
    })
    .onUpdate((event) => {
      // When at full and content is scrolled down, don't drag the sheet
      if (isAtFull.value && scrollOffset.value > 0) {
        return;
      }

      const newY = context.value + event.translationY;
      // Clamp between full and collapsed
      translateY.value = Math.max(fullY, Math.min(collapsedY, newY));
    })
    .onEnd((event) => {
      // If content is scrolled, don't snap
      if (isAtFull.value && scrollOffset.value > 0) {
        return;
      }
      snapToNearest(translateY.value, event.velocityY);
    })
    .activeOffsetY([-10, 10]);

  // -------------------------------------------------------------------------
  // Animated styles
  // -------------------------------------------------------------------------
  const animatedSheetStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
  }));

  // -------------------------------------------------------------------------
  // Search bar press — expand to full if at half
  // -------------------------------------------------------------------------
  const handleSearchPress = () => {
    showToast('Coming soon');
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <GestureDetector gesture={panGesture}>
      <Animated.View style={[styles.container, { height: screenHeight }, animatedSheetStyle]}>
        <BlurView intensity={20} tint="light" style={styles.blur}>
          {/* Grab handle pill */}
          <View style={styles.handleRow}>
            <View style={styles.handle} />
          </View>

          {/* Search + Settings row (always visible) */}
          <View style={styles.controlsRow}>
            <Pressable
              style={styles.searchBar}
              onPress={handleSearchPress}
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

          {/* Content area: loading state or scrollable children */}
          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={textColors.onSurfaceVariant} />
            </View>
          ) : (
            <Animated.ScrollView
              ref={scrollRef}
              style={styles.scrollView}
              contentContainerStyle={styles.scrollContent}
              scrollEnabled={canScroll}
              showsVerticalScrollIndicator={false}
              onScroll={scrollHandler}
              scrollEventThrottle={16}
              bounces={false}
            >
              {children}
            </Animated.ScrollView>
          )}
        </BlurView>
      </Animated.View>
    </GestureDetector>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    overflow: 'hidden',
    ...shadows.sheetAbove,
  },
  blur: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.85)',
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
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: spacing.s6,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: spacing.s4,
  },
});
