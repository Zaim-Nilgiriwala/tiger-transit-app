/**
 * Redux Store Configuration
 *
 * Combines all 6 slices matching the PRD Section 7.1 AppState shape:
 * routes, vehicles, predictions, ui, preferences, alerts.
 *
 * Exports typed hooks for use throughout the app.
 */
import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

import routesReducer from './slices/routesSlice';
import vehiclesReducer from './slices/vehiclesSlice';
import predictionsReducer from './slices/predictionsSlice';
import uiReducer from './slices/uiSlice';
import preferencesReducer from './slices/preferencesSlice';
import alertsReducer from './slices/alertsSlice';

export const store = configureStore({
  reducer: {
    routes: routesReducer,
    vehicles: vehiclesReducer,
    predictions: predictionsReducer,
    ui: uiReducer,
    preferences: preferencesReducer,
    alerts: alertsReducer,
  },
});

/** Inferred root state type from the store */
export type RootState = ReturnType<typeof store.getState>;

/** Inferred dispatch type from the store */
export type AppDispatch = typeof store.dispatch;

/** Typed dispatch hook */
export const useAppDispatch: () => AppDispatch = useDispatch;

/** Typed selector hook */
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
