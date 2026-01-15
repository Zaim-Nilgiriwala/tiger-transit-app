import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { createError } from '../middleware/error-handler';

const router = Router();
const prisma = new PrismaClient();

// GET /stops - List all stops (with optional bbox filtering)
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { north, south, east, west, limit = '200' } = req.query;

    let stops;

    if (north && south && east && west) {
      // Filter by bounding box
      stops = await prisma.stop.findMany({
        where: {
          lat: {
            gte: parseFloat(south as string),
            lte: parseFloat(north as string)
          },
          lon: {
            gte: parseFloat(west as string),
            lte: parseFloat(east as string)
          }
        },
        take: parseInt(limit as string),
        orderBy: { name: 'asc' }
      });
    } else {
      // Get all stops
      stops = await prisma.stop.findMany({
        take: parseInt(limit as string),
        orderBy: { name: 'asc' }
      });
    }

    res.json({
      success: true,
      data: stops.map(stop => ({
        id: stop.id,
        name: stop.name,
        code: stop.code,
        lat: Number(stop.lat),
        lon: Number(stop.lon),
        wheelchairAccessible: stop.wheelchairBoarding === 1,
        isMajorStop: stop.isMajorStop
      })),
      meta: {
        timestamp: new Date().toISOString(),
        count: stops.length
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /stops/route-mappings - Get mapping of stop IDs to route IDs they serve
router.get('/route-mappings', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const mappings: Record<string, string[]> = {};

    // Get all unique stop-route combinations using correct table/column names
    const stopRoutes = await prisma.$queryRaw<Array<{ stop_id: string; route_id: string }>>`
      SELECT DISTINCT st.stop_id, t.route_id
      FROM stop_times st
      JOIN trips t ON st.trip_id = t.trip_id
    `;

    stopRoutes.forEach(({ stop_id, route_id }) => {
      if (!mappings[stop_id]) {
        mappings[stop_id] = [];
      }
      if (!mappings[stop_id].includes(route_id)) {
        mappings[stop_id].push(route_id);
      }
    });

    res.json({
      success: true,
      data: mappings,
      meta: {
        timestamp: new Date().toISOString(),
        stopCount: Object.keys(mappings).length
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /stops/nearby - Get stops near a location
router.get('/nearby', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { lat, lon, radius = '500' } = req.query;

    if (!lat || !lon) {
      throw createError('Missing required parameters: lat, lon', 400, 'MISSING_PARAMETERS');
    }

    const latitude = parseFloat(lat as string);
    const longitude = parseFloat(lon as string);
    const radiusMeters = parseInt(radius as string);

    // Simple bounding box calculation (approximate)
    // 1 degree latitude ≈ 111km
    const latDelta = (radiusMeters / 111000);
    const lonDelta = (radiusMeters / (111000 * Math.cos(latitude * Math.PI / 180)));

    const stops = await prisma.stop.findMany({
      where: {
        lat: {
          gte: latitude - latDelta,
          lte: latitude + latDelta
        },
        lon: {
          gte: longitude - lonDelta,
          lte: longitude + lonDelta
        }
      }
    });

    // Calculate actual distance and filter
    const stopsWithDistance = stops.map(stop => {
      const stopLat = Number(stop.lat);
      const stopLon = Number(stop.lon);
      const distance = calculateDistance(latitude, longitude, stopLat, stopLon);

      return {
        id: stop.id,
        name: stop.name,
        code: stop.code,
        lat: stopLat,
        lon: stopLon,
        distance: Math.round(distance),
        wheelchairAccessible: stop.wheelchairBoarding === 1
      };
    }).filter(stop => stop.distance <= radiusMeters)
      .sort((a, b) => a.distance - b.distance);

    res.json({
      success: true,
      data: stopsWithDistance,
      meta: {
        timestamp: new Date().toISOString(),
        count: stopsWithDistance.length,
        radius: radiusMeters
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /stops/:id - Get stop details
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params;

    const stop = await prisma.stop.findUnique({
      where: { id },
      include: {
        stopTimes: {
          include: {
            trip: {
              include: {
                route: true
              }
            }
          },
          take: 1
        }
      }
    });

    if (!stop) {
      throw createError(`Stop with ID '${id}' not found`, 404, 'STOP_NOT_FOUND');
    }

    // Get unique routes serving this stop
    const uniqueRoutes = new Map();
    stop.stopTimes.forEach(st => {
      const route = st.trip.route;
      if (!uniqueRoutes.has(route.id)) {
        uniqueRoutes.set(route.id, {
          id: route.id,
          shortName: route.shortName,
          longName: route.longName,
          color: route.color,
          textColor: route.textColor
        });
      }
    });

    res.json({
      success: true,
      data: {
        id: stop.id,
        name: stop.name,
        code: stop.code,
        lat: Number(stop.lat),
        lon: Number(stop.lon),
        wheelchairAccessible: stop.wheelchairBoarding === 1,
        routes: Array.from(uniqueRoutes.values())
      },
      meta: {
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /stops/:id/routes - Get all routes serving this stop
router.get('/:id/routes', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params;

    const stopTimes = await prisma.stopTime.findMany({
      where: { stopId: id },
      include: {
        trip: {
          include: {
            route: true
          }
        }
      },
      distinct: ['tripId']
    });

    if (stopTimes.length === 0) {
      throw createError(`Stop with ID '${id}' not found or has no routes`, 404, 'STOP_NOT_FOUND');
    }

    // Get unique routes
    const uniqueRoutes = new Map();
    stopTimes.forEach(st => {
      const route = st.trip.route;
      if (!uniqueRoutes.has(route.id)) {
        uniqueRoutes.set(route.id, {
          id: route.id,
          shortName: route.shortName,
          longName: route.longName,
          color: route.color,
          textColor: route.textColor
        });
      }
    });

    res.json({
      success: true,
      data: Array.from(uniqueRoutes.values()),
      meta: {
        timestamp: new Date().toISOString(),
        count: uniqueRoutes.size
      }
    });
  } catch (error) {
    next(error);
  }
});

// Helper function to calculate distance between two coordinates (Haversine formula)
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000; // Earth's radius in meters
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

export { router as stopsRouter };
