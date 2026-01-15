# Tiger Transit - Quick Start Guide

## Step 1: Install Prerequisites

### Install Node.js
1. Download Node.js 20 LTS from: https://nodejs.org/
2. Run the installer and follow the setup wizard
3. Verify installation:
   ```bash
   node --version
   npm --version
   ```

### Install Docker Desktop
1. Download Docker Desktop from: https://www.docker.com/products/docker-desktop
2. Install and start Docker Desktop
3. Verify installation:
   ```bash
   docker --version
   docker-compose --version
   ```

## Step 2: Set Up the Backend

### Install Dependencies
```bash
cd backend
npm install
```

### Start Database Services
From the project root directory:
```bash
docker-compose up -d
```

This starts PostgreSQL (port 5432) and Redis (port 6379).

### Initialize Database
```bash
cd backend
npx prisma migrate dev --name init
npx prisma generate
```

### Import GTFS Data
```bash
npm run import:gtfs
```

This imports all Auburn Transit data:
- 40+ bus routes
- 178 stops
- 1,041+ trips
- 8,269+ stop times
- 16,638+ shape points

Expected output:
```
Starting GTFS import...

Importing agency data...
✓ Imported 1 agencies

Importing routes...
✓ Imported 40 routes

Importing stops...
✓ Imported 178 stops

... etc
```

### Start the Backend Server
```bash
npm run dev
```

You should see:
```
Tiger Transit API running on port 3000
Environment: development
GPS Enabled: false
```

## Step 3: Test the API

Open your browser or use curl to test endpoints:

### Health Check
```
http://localhost:3000/health
```

### Get All Routes
```
http://localhost:3000/routes
```

Expected response:
```json
{
  "success": true,
  "data": [
    {
      "id": "242",
      "shortName": "SS",
      "longName": "Security Shuttle",
      "color": "FF8822",
      "textColor": null,
      "routeType": 3,
      "agency": "Auburn University"
    },
    ...
  ],
  "meta": {
    "timestamp": "2026-01-12T...",
    "count": 40
  }
}
```

### Get College Loop Route Details
```
http://localhost:3000/routes/11
```

### Get Stops Near Student Center
```
http://localhost:3000/stops/nearby?lat=32.6024&lon=-85.4876&radius=500
```

## Step 4: Verify Database Contents

### Using Prisma Studio
```bash
cd backend
npm run prisma:studio
```

This opens a visual database browser at `http://localhost:5555`

You can browse:
- Routes table (40 routes)
- Stops table (178 stops)
- Trips table (1,041+ trips)
- Stop Times table (8,269+ records)
- Shapes table (16,638+ points)

## Troubleshooting

### Port Already in Use
If you see "Port 3000 already in use":
```bash
# Change PORT in backend/.env
PORT=3001
```

### Docker Services Won't Start
```bash
# Check Docker is running
docker ps

# Stop existing containers
docker-compose down

# Start fresh
docker-compose up -d
```

### Database Connection Error
```bash
# Check PostgreSQL is running
docker-compose ps

# Check connection
docker-compose exec postgres psql -U transit -d tigertransit -c "SELECT 1"
```

### GTFS Import Fails
Make sure the `gtfs_data/` directory exists with all files:
- agency.txt
- routes.txt
- stops.txt
- trips.txt
- stop_times.txt
- shapes.txt
- calendar.txt

## Next Steps

Once the backend is running successfully:

1. **Explore the API** - Try different endpoints and query parameters
2. **Mobile App Setup** - Begin Phase 2 of implementation
3. **Schedule-based ETAs** - Implement arrival predictions
4. **Real-time Infrastructure** - Prepare for GPS integration

## Useful Commands

```bash
# Backend development
cd backend
npm run dev              # Start development server
npm run build            # Build for production
npm start                # Run production build

# Database
npm run prisma:studio    # Open database browser
npm run prisma:migrate   # Run migrations
npx prisma migrate reset # Reset database

# Docker
docker-compose up -d     # Start services
docker-compose down      # Stop services
docker-compose logs      # View logs
docker-compose ps        # Check status

# GTFS
npm run import:gtfs      # Import transit data
```

## API Documentation

See [README.md](README.md) for complete API endpoint documentation.

## Need Help?

- Check [README.md](README.md) for architecture details
- Review [backend/src/routes/](backend/src/routes/) for API implementation
- Examine [prisma/schema.prisma](backend/prisma/schema.prisma) for database schema
- Look at the plan file: `.claude/plans/delightful-baking-liskov.md`
