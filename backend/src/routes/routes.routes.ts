import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { createError } from '../middleware/error-handler';

const router = Router();
const prisma = new PrismaClient();

// Decode Google encoded polyline to array of coordinates
function decodePolyline(encoded: string): Array<{ lat: number; lon: number }> {
  const coordinates: Array<{ lat: number; lon: number }> = [];
  let index = 0;
  let lat = 0;
  let lon = 0;

  while (index < encoded.length) {
    let shift = 0;
    let result = 0;
    let byte: number;

    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const dlat = result & 1 ? ~(result >> 1) : result >> 1;
    lat += dlat;

    shift = 0;
    result = 0;

    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const dlon = result & 1 ? ~(result >> 1) : result >> 1;
    lon += dlon;

    coordinates.push({
      lat: lat / 1e5,
      lon: lon / 1e5
    });
  }

  return coordinates;
}

// GET /routes - List all active routes
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const routes = await prisma.route.findMany({
      where: { isActive: true },
      include: {
        agency: {
          select: {
            name: true,
            timezone: true
          }
        }
      },
      orderBy: { sortOrder: 'asc' }
    });

    res.json({
      success: true,
      data: routes.map(route => ({
        id: route.id,
        shortName: route.shortName,
        longName: route.longName,
        color: route.color,
        textColor: route.textColor,
        routeType: route.routeType,
        agency: route.agency.name
      })),
      meta: {
        timestamp: new Date().toISOString(),
        count: routes.length
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /routes/:id - Get route details
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params;

    const route = await prisma.route.findUnique({
      where: { id },
      include: {
        agency: true,
        trips: {
          include: {
            stopTimes: {
              include: {
                stop: true
              },
              orderBy: { stopSequence: 'asc' }
            }
          },
          take: 1 // Get one trip to extract stop sequence
        }
      }
    });

    if (!route) {
      throw createError(`Route with ID '${id}' not found`, 404, 'ROUTE_NOT_FOUND');
    }

    // Extract unique stops from the first trip
    const stops = route.trips[0]?.stopTimes.map(st => ({
      id: st.stop.id,
      name: st.stop.name,
      code: st.stop.code,
      lat: Number(st.stop.lat),
      lon: Number(st.stop.lon),
      sequence: st.stopSequence
    })) || [];

    res.json({
      success: true,
      data: {
        id: route.id,
        shortName: route.shortName,
        longName: route.longName,
        color: route.color,
        textColor: route.textColor,
        routeType: route.routeType,
        agency: {
          name: route.agency.name,
          timezone: route.agency.timezone
        },
        stops
      },
      meta: {
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /routes/:id/shape - Get route geometry
router.get('/:id/shape', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params;
    const { direction = '0' } = req.query;

    // First check if pre-computed geometry exists
    const geometry = await prisma.routeGeometry.findFirst({
      where: {
        routeId: id,
        directionId: parseInt(direction as string)
      }
    });

    if (geometry) {
      const coordinates = decodePolyline(geometry.encodedPolyline);
      return res.json({
        success: true,
        data: {
          routeId: id,
          directionId: geometry.directionId,
          coordinates,
          bounds: geometry.bounds
        },
        meta: {
          timestamp: new Date().toISOString(),
          cached: true,
          pointCount: coordinates.length
        }
      });
    }

    // If not cached, get shape points from a trip
    // First try with the specified direction, then try with null direction, then try any direction
    let trip = await prisma.trip.findFirst({
      where: {
        routeId: id,
        directionId: parseInt(direction as string),
        shapeId: { not: null }
      }
    });

    // If not found, try with null directionId (some routes don't have direction set)
    if (!trip) {
      trip = await prisma.trip.findFirst({
        where: {
          routeId: id,
          directionId: null,
          shapeId: { not: null }
        }
      });
    }

    // If still not found, try any trip with a shape for this route
    if (!trip) {
      trip = await prisma.trip.findFirst({
        where: {
          routeId: id,
          shapeId: { not: null }
        }
      });
    }

    if (!trip || !trip.shapeId) {
      throw createError(`No shape found for route '${id}'`, 404, 'SHAPE_NOT_FOUND');
    }

    const shapePoints = await prisma.shape.findMany({
      where: { id: trip.shapeId },
      orderBy: { ptSequence: 'asc' }
    });

    const coordinates = shapePoints.map(pt => ({
      lat: Number(pt.ptLat),
      lon: Number(pt.ptLon)
    }));

    res.json({
      success: true,
      data: {
        routeId: id,
        directionId: parseInt(direction as string),
        shapeId: trip.shapeId,
        coordinates
      },
      meta: {
        timestamp: new Date().toISOString(),
        cached: false,
        pointCount: coordinates.length
      }
    });
  } catch (error) {
    next(error);
  }
});

export { router as routesRouter };
