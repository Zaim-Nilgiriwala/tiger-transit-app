import { configureStore } from '@reduxjs/toolkit';
import { transitApi } from './api/transitApi';
import routesReducer from './slices/routesSlice';

export const store = configureStore({
  reducer: {
    [transitApi.reducerPath]: transitApi.reducer,
    routes: routesReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(transitApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
