/**
 * Vehicles Slice
 *
 * Manages real-time vehicle positions from GTFS-RT position feed.
 * Updated every 5 seconds while the app is in the foreground.
 *
 * PRD Section 7.1: AppState.vehicles
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { VehiclePosition } from '../../types/gtfs.types';

interface VehiclesState {
  positions: VehiclePosition[];
  lastUpdated: number;
  connected: boolean;
}

const initialState: VehiclesState = {
  positions: [],
  lastUpdated: 0,
  connected: false,
};

export const vehiclesSlice = createSlice({
  name: 'vehicles',
  initialState,
  reducers: {
    setPositions(state, action: PayloadAction<VehiclePosition[]>) {
      state.positions = action.payload;
      state.lastUpdated = Date.now();
    },
    setConnected(state, action: PayloadAction<boolean>) {
      state.connected = action.payload;
    },
    clearPositions(state) {
      state.positions = [];
      state.lastUpdated = 0;
    },
  },
});

export const { setPositions, setConnected, clearPositions } =
  vehiclesSlice.actions;

export default vehiclesSlice.reducer;
