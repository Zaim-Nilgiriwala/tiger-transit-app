import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Route } from '../../types/gtfs.types';

interface RoutesState {
  selectedRoute: Route | null;
  visibleRoutes: Route[];
}

const initialState: RoutesState = {
  selectedRoute: null,
  visibleRoutes: [],
};

const routesSlice = createSlice({
  name: 'routes',
  initialState,
  reducers: {
    setSelectedRoute: (state, action: PayloadAction<Route | null>) => {
      state.selectedRoute = action.payload;
    },
    setVisibleRoutes: (state, action: PayloadAction<Route[]>) => {
      state.visibleRoutes = action.payload;
    },
  },
});

export const { setSelectedRoute, setVisibleRoutes } = routesSlice.actions;
export default routesSlice.reducer;
