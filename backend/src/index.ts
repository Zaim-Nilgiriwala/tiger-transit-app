import express from 'express';
import { createServer } from 'http';
import { Server as SocketServer } from 'socket.io';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';
import dotenv from 'dotenv';
import { errorHandler } from './middleware/error-handler';
import { routesRouter } from './routes/routes.routes';
import { stopsRouter } from './routes/stops.routes';
import { healthRouter } from './routes/health.routes';
import { vehiclesRouter } from './routes/vehicles.routes';
import { etaSpotService, VehiclePosition } from './services/etaspot.service';

dotenv.config();

const app = express();
const httpServer = createServer(app);
const PORT = process.env.PORT || 3000;

// Socket.IO setup
const io = new SocketServer(httpServer, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

// Middleware
app.use(helmet());
app.use(cors({
  origin: process.env.CORS_ORIGIN || '*',
  credentials: true
}));
app.use(compression());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Request logging
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

// Routes
app.use('/health', healthRouter);
app.use('/routes', routesRouter);
app.use('/stops', stopsRouter);
app.use('/vehicles', vehiclesRouter);

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: {
      code: 'NOT_FOUND',
      message: `Route ${req.method} ${req.path} not found`
    }
  });
});

// Error handler
app.use(errorHandler);

// Socket.IO connection handling
io.on('connection', (socket) => {
  console.log(`Client connected: ${socket.id}`);

  // Subscribe to all vehicle updates
  socket.on('subscribe:all', () => {
    socket.join('all-vehicles');
    console.log(`${socket.id} subscribed to all vehicles`);
    // Send current vehicles immediately
    const vehicles = etaSpotService.getVehicles();
    socket.emit('vehicles', vehicles);
  });

  // Subscribe to specific route updates
  socket.on('subscribe:route', (routeId: string) => {
    socket.join(`route:${routeId}`);
    console.log(`${socket.id} subscribed to route ${routeId}`);
    // Send current vehicles for this route
    const vehicles = etaSpotService.getVehiclesByRoute(routeId);
    socket.emit('vehicles', vehicles);
  });

  // Unsubscribe from route
  socket.on('unsubscribe:route', (routeId: string) => {
    socket.leave(`route:${routeId}`);
    console.log(`${socket.id} unsubscribed from route ${routeId}`);
  });

  // Subscribe to stop arrivals
  socket.on('subscribe:stop', (stopId: string) => {
    socket.join(`stop:${stopId}`);
    console.log(`${socket.id} subscribed to stop ${stopId}`);
    // Send current vehicles heading to this stop
    const vehicles = etaSpotService.getVehiclesByStop(stopId);
    socket.emit('arrivals', vehicles);
  });

  // Unsubscribe from stop
  socket.on('unsubscribe:stop', (stopId: string) => {
    socket.leave(`stop:${stopId}`);
    console.log(`${socket.id} unsubscribed from stop ${stopId}`);
  });

  socket.on('disconnect', () => {
    console.log(`Client disconnected: ${socket.id}`);
  });
});

// ETA SPOT event handlers
etaSpotService.on('vehicle', (vehicle: VehiclePosition) => {
  // Broadcast to all vehicles room
  io.to('all-vehicles').emit('vehicle', vehicle);

  // Broadcast to specific route room
  io.to(`route:${vehicle.routeId}`).emit('vehicle', vehicle);

  // Broadcast to stop room if vehicle is heading there
  if (vehicle.nextStopId) {
    io.to(`stop:${vehicle.nextStopId}`).emit('arrival', vehicle);
  }
});

etaSpotService.on('connected', () => {
  console.log('ETA SPOT service connected');
  io.emit('status', { connected: true });
});

etaSpotService.on('disconnected', (reason: string) => {
  console.log('ETA SPOT service disconnected:', reason);
  io.emit('status', { connected: false, reason });
});

// Periodic broadcast of all vehicles (every 3 seconds)
setInterval(() => {
  const vehicles = etaSpotService.getVehicles();
  if (vehicles.length > 0) {
    io.to('all-vehicles').emit('vehicles', vehicles);
  }
}, 3000);

// Start server
httpServer.listen(PORT, () => {
  console.log(`Tiger Transit API running on port ${PORT}`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`WebSocket enabled on port ${PORT}`);

  // Connect to ETA SPOT if cookie is configured
  if (process.env.ETASPOT_COOKIE) {
    console.log('Connecting to ETA SPOT for live vehicle data...');
    etaSpotService.connect();
  } else {
    console.log('ETASPOT_COOKIE not set - live vehicle tracking disabled');
  }
});
