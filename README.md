2# Tiger Transit Mobile App

A modern React Native mobile app for Auburn University's Tiger Transit system, replacing the ETA SPOT application.

## Project Structure

```
Tiger Transit/
├── backend/              # Node.js + Express backend API
│   ├── src/
│   │   ├── routes/      # API route handlers
│   │   ├── services/    # Business logic
│   │   ├── middleware/  # Express middleware
│   │   └── index.ts     # Main application entry
│   ├── prisma/          # Database schema
│   ├── scripts/         # Utility scripts (GTFS import)
│   └── package.json
├── mobile/              # React Native mobile app (coming soon)
├── gtfs_data/           # GTFS transit data files
└── docker-compose.yml   # Development environment setup
```

## Technology Stack

### Backend
- **Node.js 20** with Express.js and TypeScript
- **PostgreSQL 15+ with PostGIS** for geospatial data
- **Redis** for caching and real-time features
- **Prisma ORM** for type-safe database access
- **Socket.IO** for WebSocket communication (future)

### Mobile (Coming Soon)
- React Native with TypeScript
- Redux Toolkit for state management
- React Navigation for routing
- react-native-maps for mapping

## Getting Started

### Prerequisites

- Node.js 20+
- Docker and Docker Compose
- npm or yarn

### Installation

1. **Install backend dependencies:**
   ```bash
   cd backend
   npm install
   ```

2. **Start the development environment:**
   ```bash
   # From the root directory
   docker-compose up -d
   ```

   This will start:
   - PostgreSQL with PostGIS on port 5432
   - Redis on port 6379

3. **Run database migrations:**
   ```bash
   cd backend
   npx prisma migrate dev
   ```

4. **Import GTFS data:**
   ```bash
   cd backend
   npm run import:gtfs
   ```

   This will import all transit data from the `gtfs_data/` directory into PostgreSQL.

5. **Start the backend server:**
   ```bash
   cd backend
   npm run dev
   ```

   The API will be running at `http://localhost:3000`

### API Endpoints

#### Health Check
```
GET /health
```

#### Routes
```
GET /routes              # List all active routes
GET /routes/:id          # Get route details with stops
GET /routes/:id/shape    # Get route polyline geometry
```

#### Stops
```
GET /stops                                    # List all stops
GET /stops?north=X&south=Y&east=Z&west=W      # Filter by bounding box
GET /stops/nearby?lat=X&lon=Y&radius=500      # Get nearby stops
GET /stops/:id                                 # Get stop details
GET /stops/:id/routes                         # Get routes serving stop
```

### Example API Requests

```bash
# Health check
curl http://localhost:3000/health

# Get all routes
curl http://localhost:3000/routes

# Get route details
curl http://localhost:3000/routes/11

# Get stops near Auburn University
curl "http://localhost:3000/stops/nearby?lat=32.6024&lon=-85.4876&radius=500"
```

## GTFS Data

The project uses Auburn University's GTFS (General Transit Feed Specification) data:

- **40+ routes** including campus shuttles, game day services, and off-campus routes
- **178 stops** across Auburn campus and city
- **1,041+ trips** with full schedules
- **8,269+ stop times** for arrival predictions
- **16,638+ shape points** for route polylines on map

## Development

### Database Management

```bash
# Open Prisma Studio (visual database editor)
cd backend
npm run prisma:studio

# Create a new migration
npm run prisma:migrate

# Reset database
npx prisma migrate reset
```

### Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

```env
DATABASE_URL="postgresql://transit:transit_dev@localhost:5432/tigertransit"
REDIS_URL="redis://localhost:6379"
PORT=3000
NODE_ENV=development
GPS_ENABLED=false
```

## Architecture Highlights

### GPS Provider Abstraction
The backend is designed with a flexible GPS provider abstraction layer to accommodate future real-time vehicle tracking, regardless of the GPS data format:

- Works fully with GTFS schedule data initially
- Ready for real-time GPS integration when available
- Supports multiple GPS providers (GTFS-Realtime, WebSocket, HTTP polling, custom)
- Configurable field mapping for any data format

### Real-Time Ready
- WebSocket infrastructure prepared with Socket.IO
- Redis caching layer for vehicle positions
- Hybrid ETA system (schedule-based now, real-time when GPS available)

## Implementation Phases

✅ **Phase 1: Backend Foundation** (Current)
- Node.js/Express setup with TypeScript
- PostgreSQL with PostGIS and Redis via Docker
- Prisma schema for GTFS data
- GTFS data importer
- Basic REST API endpoints

⏳ **Phase 2: Mobile App Foundation** (Next)
- React Native project initialization
- Navigation structure
- Map view with route polylines
- API integration

🔜 **Phase 3-9: Core Features & Launch**
- Stop markers and search
- Schedule-based ETAs
- Favorites and offline support
- Real-time infrastructure
- Polish and deployment

## Project Timeline

- **Weeks 1-2**: Backend + GTFS foundation, mobile setup ✅ Week 1 Complete
- **Weeks 3-4**: Core transit features (stops, routes, navigation)
- **Week 5**: Schedule-based ETA system
- **Week 6**: Favorites and offline support
- **Weeks 7-8**: Real-time infrastructure preparation
- **Weeks 9-10**: Polish, testing, deployment
- **Future**: Real-time GPS integration when data becomes available

## Resources

- [GTFS Specification](https://gtfs.org/)
- [Prisma Documentation](https://www.prisma.io/docs)
- [React Native Documentation](https://reactnative.dev/)
- [Auburn Transit Website](https://www.auburn.edu/administration/parking_transit/transit/)

## License

MIT
