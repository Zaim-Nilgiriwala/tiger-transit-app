import { Route, Stop } from './gtfs.types';

export type RootStackParamList = {
  Main: undefined;
  RouteDetail: { routeId: string };
  StopDetail: { stopId: string };
};

export type TabParamList = {
  Map: undefined;
  Routes: undefined;
  Settings: undefined;
};
