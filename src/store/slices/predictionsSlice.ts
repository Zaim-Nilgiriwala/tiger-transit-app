/**
 * Predictions Slice
 *
 * Manages ETA predictions by stop, from either the XGBoost model
 * or GTFS-RT trip update fallback.
 *
 * PRD Section 7.1: AppState.predictions
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { ArrivalPrediction } from '../../types/gtfs.types';

interface PredictionsState {
  byStop: Record<string, ArrivalPrediction[]>;
  loading: boolean;
}

const initialState: PredictionsState = {
  byStop: {},
  loading: false,
};

export const predictionsSlice = createSlice({
  name: 'predictions',
  initialState,
  reducers: {
    setPredictions(
      state,
      action: PayloadAction<{
        stopId: string;
        predictions: ArrivalPrediction[];
      }>
    ) {
      state.byStop[action.payload.stopId] = action.payload.predictions;
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload;
    },
    clearPredictions(state) {
      state.byStop = {};
    },
  },
});

export const { setPredictions, setLoading, clearPredictions } =
  predictionsSlice.actions;

export default predictionsSlice.reducer;
