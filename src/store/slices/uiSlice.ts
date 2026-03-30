/**
 * UI Slice
 *
 * Manages transient UI state: selected route/stop, sheet position,
 * favorites filter, and active callout bubble.
 *
 * PRD Section 7.1: AppState.ui
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type SheetPosition = 'collapsed' | 'half' | 'full';

interface ActiveCallout {
  type: 'bus' | 'stop';
  id: string;
}

interface UIState {
  selectedRouteId: string | null;
  selectedStopId: string | null;
  sheetPosition: SheetPosition;
  showFavoritesOnly: boolean;
  activeCallout: ActiveCallout | null;
}

const initialState: UIState = {
  selectedRouteId: null,
  selectedStopId: null,
  sheetPosition: 'collapsed',
  showFavoritesOnly: false,
  activeCallout: null,
};

export const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    selectRoute(state, action: PayloadAction<string | null>) {
      // Clear stop selection when changing routes
      if (action.payload !== state.selectedRouteId) {
        state.selectedStopId = null;
      }
      state.selectedRouteId = action.payload;
    },
    selectStop(state, action: PayloadAction<string | null>) {
      state.selectedStopId = action.payload;
    },
    setSheetPosition(state, action: PayloadAction<SheetPosition>) {
      state.sheetPosition = action.payload;
    },
    toggleFavoritesOnly(state) {
      state.showFavoritesOnly = !state.showFavoritesOnly;
    },
    setActiveCallout(state, action: PayloadAction<ActiveCallout | null>) {
      state.activeCallout = action.payload;
    },
    clearCallout(state) {
      state.activeCallout = null;
    },
  },
});

export const {
  selectRoute,
  selectStop,
  setSheetPosition,
  toggleFavoritesOnly,
  setActiveCallout,
  clearCallout,
} = uiSlice.actions;

export default uiSlice.reducer;
