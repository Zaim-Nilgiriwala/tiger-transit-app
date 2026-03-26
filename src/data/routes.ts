/**
 * Bundled Static GTFS Route Data
 *
 * Converted from ETA-Model/gtfs_data/routes.txt into a typed TypeScript constant.
 * Synchronous import -- no async loading required. Route changes require an app update
 * (Auburn changes routes ~2x per year).
 *
 * All 39 routes from the GTFS feed. routeColor values are prefixed with '#'.
 */
import { Route } from '../types/gtfs.types';

export const ROUTES: Route[] = [
  { routeId: '242', shortName: 'SS', longName: 'Security Shuttle', routeColor: '#FF8822', routeType: 3 },
  { routeId: '11', shortName: 'CL', longName: 'College Loop', routeColor: '#5BA528', routeType: 3 },
  { routeId: '5', shortName: 'EG', longName: 'East Glenn', routeColor: '#047EF8', routeType: 3 },
  { routeId: '27', shortName: 'FSS', longName: 'Friday Evening Shopping Shuttle', routeColor: '#CC6633', routeType: 3 },
  { routeId: '26', shortName: 'GH', longName: 'Glenn-Harper', routeColor: '#BA9D57', routeType: 3 },
  { routeId: '2', shortName: 'HW', longName: 'Haley West', routeColor: '#C00C00', routeType: 3 },
  { routeId: '33', shortName: 'HSS', longName: 'Health Sciences Sector', routeColor: '#DB4444', routeType: 3 },
  { routeId: '31', shortName: 'ML', longName: 'Magnolia', routeColor: '#18857A', routeType: 3 },
  { routeId: '99', shortName: 'NA', longName: 'North Auburn', routeColor: '#820000', routeType: 3 },
  { routeId: '7', shortName: 'NC', longName: 'North College', routeColor: '#8470FF', routeType: 3 },
  { routeId: '93', shortName: 'ND', longName: 'North Dean -AM  (before 11 am)', routeColor: '#FF0000', routeType: 3 },
  { routeId: '235_93', shortName: 'NDPM', longName: 'North Dean - PM (after 11 am)', routeColor: '#FF0000', routeType: 3 },
  { routeId: '97', shortName: 'NDON', longName: 'North Donahue', routeColor: '#AFBAC1', routeType: 3 },
  { routeId: '24', shortName: 'NRS', longName: 'North Ross', routeColor: '#B15842', routeType: 3 },
  { routeId: '17', shortName: 'OR', longName: 'Old Row - West Parking', routeColor: '#D5A168', routeType: 3 },
  { routeId: '96', shortName: 'PNR', longName: 'Park & Ride', routeColor: '#0265AC', routeType: 3 },
  { routeId: '4', shortName: 'SSJ', longName: 'Samford-Shug Jordan', routeColor: '#950714', routeType: 3 },
  { routeId: '215_202_201_156', shortName: 'SA', longName: 'South Auburn', routeColor: '#6578AD', routeType: 3 },
  { routeId: '28', shortName: 'SC', longName: 'South College', routeColor: '#5DBEEC', routeType: 3 },
  { routeId: '100', shortName: 'SD', longName: 'South Donahue', routeColor: '#D00000', routeType: 3 },
  { routeId: '226_32', shortName: 'SQFA', longName: 'South Quad/Fine Arts', routeColor: '#B949F1', routeType: 3 },
  { routeId: '1', shortName: 'WBR', longName: 'Webster Road', routeColor: '#330066', routeType: 3 },
  { routeId: '9', shortName: 'WC', longName: 'West Campus', routeColor: '#009E80', routeType: 3 },
  { routeId: '6', shortName: 'WG', longName: 'West Glenn', routeColor: '#F28500', routeType: 3 },
  { routeId: '114', shortName: 'WR', longName: 'Wire Road', routeColor: '#E6E600', routeType: 3 },
  { routeId: '216', shortName: 'GVCOM', longName: 'GDS - ADA @ VCOM', routeColor: '#76DD28', routeType: 3 },
  { routeId: '217', shortName: 'GAM', longName: 'GDS - Auburn Mall', routeColor: '#F5F518', routeType: 3 },
  { routeId: '218', shortName: 'GASC', longName: 'GDS - Auburn Softball Complex', routeColor: '#58D9DD', routeType: 3 },
  { routeId: '227_', shortName: 'GASC1', longName: 'GDS - 2nd Half Auburn Softball Complex', routeColor: '#58D9DD', routeType: 3 },
  { routeId: '225_', shortName: 'GDSP', longName: 'GDS - Duck Samford Park', routeColor: '#DD66D1', routeType: 3 },
  { routeId: '220', shortName: 'GFAC', longName: 'GDS - Facilities', routeColor: '#DD550C', routeType: 3 },
  { routeId: '228_', shortName: 'GFAC1', longName: 'GDS - 2nd Half Facilities', routeColor: '#DD550C', routeType: 3 },
  { routeId: '221', shortName: 'GPAC', longName: 'GDS - GPAC / South Quad Deck', routeColor: '#FF0000', routeType: 3 },
  { routeId: '222', shortName: 'GTT', longName: 'GDS - Tiger Town', routeColor: '#FACA5A', routeType: 3 },
  { routeId: '223', shortName: 'GWP', longName: 'GDS - West Parking', routeColor: '#38C3FF', routeType: 3 },
  { routeId: '230', shortName: 'CT', longName: 'Charter', routeColor: '#090909', routeType: 3 },
  { routeId: '241', shortName: 'Pan', longName: 'Panhellenic', routeColor: '#F49CF7', routeType: 3 },
  { routeId: '231', shortName: 'Vans', longName: 'University Express', routeColor: '#0C0C0C', routeType: 3 },
  { routeId: '232', shortName: 'JT', longName: 'jAUnt', routeColor: '#FCEC10', routeType: 3 },
];
