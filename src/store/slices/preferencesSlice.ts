/**
 * Preferences Slice
 *
 * Manages user favorites (routes and stops) that persist
 * across sessions via AsyncStorage hydration.
 *
 * PRD Section 7.1: AppState.preferences
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface PreferencesState {
  favoriteRouteIds: string[];
  favoriteStopIds: string[];
}

const initialState: PreferencesState = {
  favoriteRouteIds: [],
  favoriteStopIds: [],
};

export const preferencesSlice = createSlice({
  name: 'preferences',
  initialState,
  reducers: {
    toggleFavoriteRoute(state, action: PayloadAction<string>) {
      const routeId = action.payload;
      const index = state.favoriteRouteIds.indexOf(routeId);
      if (index === -1) {
        state.favoriteRouteIds.push(routeId);
      } else {
        state.favoriteRouteIds.splice(index, 1);
      }
    },
    toggleFavoriteStop(state, action: PayloadAction<string>) {
      const stopId = action.payload;
      const index = state.favoriteStopIds.indexOf(stopId);
      if (index === -1) {
        state.favoriteStopIds.push(stopId);
      } else {
        state.favoriteStopIds.splice(index, 1);
      }
    },
    /** Hydrate favorites from AsyncStorage on app launch */
    setFavorites(
      state,
      action: PayloadAction<{
        routeIds: string[];
        stopIds: string[];
      }>
    ) {
      state.favoriteRouteIds = action.payload.routeIds;
      state.favoriteStopIds = action.payload.stopIds;
    },
  },
});

export const { toggleFavoriteRoute, toggleFavoriteStop, setFavorites } =
  preferencesSlice.actions;

export default preferencesSlice.reducer;
