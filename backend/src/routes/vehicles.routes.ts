import { Router, Request, Response } from 'express';
import { etaSpotService } from '../services/etaspot.service';

const router = Router();

// GET /vehicles - All active vehicles
router.get('/', (req: Request, res: Response) => {
  const vehicles = etaSpotService.getVehicles();
  res.json({
    success: true,
    data: vehicles,
    meta: {
      count: vehicles.length,
      timestamp: new Date().toISOString(),
      connected: etaSpotService.isServiceConnected()
    }
  });
});

// GET /vehicles/route/:routeId - Vehicles on specific route
router.get('/route/:routeId', (req: Request, res: Response) => {
  const { routeId } = req.params;
  const vehicles = etaSpotService.getVehiclesByRoute(routeId);
  res.json({
    success: true,
    data: vehicles,
    meta: {
      count: vehicles.length,
      routeId,
      timestamp: new Date().toISOString()
    }
  });
});

// GET /vehicles/stop/:stopId - Vehicles approaching a stop
router.get('/stop/:stopId', (req: Request, res: Response) => {
  const { stopId } = req.params;
  const vehicles = etaSpotService.getVehiclesByStop(stopId);
  res.json({
    success: true,
    data: vehicles,
    meta: {
      count: vehicles.length,
      stopId,
      timestamp: new Date().toISOString()
    }
  });
});

// GET /vehicles/:vehicleId - Single vehicle details
router.get('/:vehicleId', (req: Request, res: Response) => {
  const { vehicleId } = req.params;
  const vehicle = etaSpotService.getVehicle(vehicleId);

  if (!vehicle) {
    return res.status(404).json({
      success: false,
      error: {
        code: 'VEHICLE_NOT_FOUND',
        message: `Vehicle ${vehicleId} not found or is not currently active`
      }
    });
  }

  res.json({
    success: true,
    data: vehicle,
    meta: {
      timestamp: new Date().toISOString()
    }
  });
});

// GET /vehicles/status - Connection status
router.get('/status', (req: Request, res: Response) => {
  res.json({
    success: true,
    data: {
      connected: etaSpotService.isServiceConnected(),
      vehicleCount: etaSpotService.getVehicleCount()
    },
    meta: {
      timestamp: new Date().toISOString()
    }
  });
});

export { router as vehiclesRouter };
