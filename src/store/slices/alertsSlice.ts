/**
 * Alerts Slice
 *
 * Manages GTFS-RT service alerts, polled every 60 seconds.
 *
 * PRD Section 7.1: AppState.alerts
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { ServiceAlert } from '../../types/gtfs.types';

interface AlertsState {
  active: ServiceAlert[];
  lastFetched: number;
}

const initialState: AlertsState = {
  active: [],
  lastFetched: 0,
};

export const alertsSlice = createSlice({
  name: 'alerts',
  initialState,
  reducers: {
    setAlerts(state, action: PayloadAction<ServiceAlert[]>) {
      state.active = action.payload;
      state.lastFetched = Date.now();
    },
    clearAlerts(state) {
      state.active = [];
    },
  },
});

export const { setAlerts, clearAlerts } = alertsSlice.actions;

export default alertsSlice.reducer;
