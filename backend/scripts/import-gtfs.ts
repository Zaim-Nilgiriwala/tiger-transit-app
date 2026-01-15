import { PrismaClient } from '@prisma/client';
import { parse } from 'csv-parse/sync';
import * as fs from 'fs';
import * as path from 'path';
// @ts-ignore - no type definitions available
import polyline from 'polyline';

const prisma = new PrismaClient();
const GTFS_DIR = path.join(__dirname, '../../gtfs_data');

interface GTFSFile {
  filename: string;
  required: boolean;
}

const GTFS_FILES: GTFSFile[] = [
  { filename: 'agency.txt', required: true },
  { filename: 'routes.txt', required: true },
  { filename: 'stops.txt', required: true },
  { filename: 'trips.txt', required: true },
  { filename: 'stop_times.txt', required: true },
  { filename: 'shapes.txt', required: false },
  { filename: 'calendar.txt', required: true },
  { filename: 'calendar_dates.txt', required: false },
];

async function importGTFS() {
  console.log('Starting GTFS import...\n');

  try {
    // Check if files exist
    for (const file of GTFS_FILES) {
      const filePath = path.join(GTFS_DIR, file.filename);
      if (!fs.existsSync(filePath)) {
        if (file.required) {
          throw new Error(`Required file ${file.filename} not found in ${GTFS_DIR}`);
        } else {
          console.log(`Optional file ${file.filename} not found, skipping...`);
        }
      }
    }

    // Import Agency
    await importAgency();

    // Import Routes
    await importRoutes();

    // Import Stops
    await importStops();

    // Import Trips
    await importTrips();

    // Import Stop Times
    await importStopTimes();

    // Import Shapes
    await importShapes();

    // Import Calendar
    await importCalendar();

    // Import Calendar Dates
    await importCalendarDates();

    // Generate Route Geometries
    await generateRouteGeometries();

    console.log('\n✅ GTFS import completed successfully!');
  } catch (error) {
    console.error('❌ GTFS import failed:', error);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

async function importAgency() {
  console.log('Importing agency data...');
  const filePath = path.join(GTFS_DIR, 'agency.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  for (const record of records) {
    await prisma.agency.upsert({
      where: { id: record.agency_id || '1' },
      update: {},
      create: {
        id: record.agency_id || '1',
        name: record.agency_name,
        url: record.agency_url || null,
        timezone: record.agency_timezone,
        lang: record.agency_lang || null,
        phone: record.agency_phone || null,
        fareUrl: record.agency_fare_url || null,
        email: record.agency_email || null
      }
    });
  }
  console.log(`✓ Imported ${records.length} agencies\n`);
}

async function importRoutes() {
  console.log('Importing routes...');
  const filePath = path.join(GTFS_DIR, 'routes.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  for (const record of records) {
    await prisma.route.upsert({
      where: { id: record.route_id },
      update: {},
      create: {
        id: record.route_id,
        agencyId: record.agency_id || '1',
        shortName: record.route_short_name || null,
        longName: record.route_long_name,
        routeType: parseInt(record.route_type),
        color: record.route_color || null,
        textColor: record.route_text_color || null,
        sortOrder: record.route_sort_order ? parseInt(record.route_sort_order) : null
      }
    });
  }
  console.log(`✓ Imported ${records.length} routes\n`);
}

async function importStops() {
  console.log('Importing stops...');
  const filePath = path.join(GTFS_DIR, 'stops.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  for (const record of records) {
    await prisma.stop.upsert({
      where: { id: record.stop_id },
      update: {},
      create: {
        id: record.stop_id,
        name: record.stop_name,
        lat: parseFloat(record.stop_lat),
        lon: parseFloat(record.stop_lon),
        code: record.stop_code || null,
        desc: record.stop_desc || null,
        wheelchairBoarding: record.wheelchair_boarding ? parseInt(record.wheelchair_boarding) : 0
      }
    });
  }
  console.log(`✓ Imported ${records.length} stops\n`);
}

async function importTrips() {
  console.log('Importing trips...');
  const filePath = path.join(GTFS_DIR, 'trips.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  let count = 0;
  for (const record of records) {
    await prisma.trip.upsert({
      where: { id: record.trip_id },
      update: {},
      create: {
        id: record.trip_id,
        routeId: record.route_id,
        serviceId: record.service_id,
        headsign: record.trip_headsign || null,
        directionId: record.direction_id ? parseInt(record.direction_id) : null,
        blockId: record.block_id || null,
        shapeId: record.shape_id || null
      }
    });
    count++;
    if (count % 100 === 0) {
      process.stdout.write(`\r  Processed ${count} trips...`);
    }
  }
  console.log(`\r✓ Imported ${records.length} trips\n`);
}

async function importStopTimes() {
  console.log('Importing stop times (this may take a while)...');
  const filePath = path.join(GTFS_DIR, 'stop_times.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  let count = 0;
  for (const record of records) {
    await prisma.stopTime.upsert({
      where: {
        tripId_stopSequence: {
          tripId: record.trip_id,
          stopSequence: parseInt(record.stop_sequence)
        }
      },
      update: {},
      create: {
        tripId: record.trip_id,
        stopId: record.stop_id,
        stopSequence: parseInt(record.stop_sequence),
        arrivalTime: record.arrival_time,
        departureTime: record.departure_time,
        shapeDistTraveled: record.shape_dist_traveled ? parseFloat(record.shape_dist_traveled) : null,
        timepoint: record.timepoint ? parseInt(record.timepoint) : 0
      }
    });
    count++;
    if (count % 500 === 0) {
      process.stdout.write(`\r  Processed ${count}/${records.length} stop times...`);
    }
  }
  console.log(`\r✓ Imported ${records.length} stop times\n`);
}

async function importShapes() {
  const filePath = path.join(GTFS_DIR, 'shapes.txt');
  if (!fs.existsSync(filePath)) {
    console.log('Shapes file not found, skipping...\n');
    return;
  }

  console.log('Importing shapes...');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  let count = 0;
  for (const record of records) {
    await prisma.shape.upsert({
      where: {
        id_ptSequence: {
          id: record.shape_id,
          ptSequence: parseInt(record.shape_pt_sequence)
        }
      },
      update: {},
      create: {
        id: record.shape_id,
        ptLat: parseFloat(record.shape_pt_lat),
        ptLon: parseFloat(record.shape_pt_lon),
        ptSequence: parseInt(record.shape_pt_sequence),
        distTraveled: record.shape_dist_traveled ? parseFloat(record.shape_dist_traveled) : null
      }
    });
    count++;
    if (count % 1000 === 0) {
      process.stdout.write(`\r  Processed ${count}/${records.length} shape points...`);
    }
  }
  console.log(`\r✓ Imported ${records.length} shape points\n`);
}

async function importCalendar() {
  console.log('Importing calendar...');
  const filePath = path.join(GTFS_DIR, 'calendar.txt');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  for (const record of records) {
    await prisma.calendar.upsert({
      where: { serviceId: record.service_id },
      update: {},
      create: {
        serviceId: record.service_id,
        monday: parseInt(record.monday),
        tuesday: parseInt(record.tuesday),
        wednesday: parseInt(record.wednesday),
        thursday: parseInt(record.thursday),
        friday: parseInt(record.friday),
        saturday: parseInt(record.saturday),
        sunday: parseInt(record.sunday),
        startDate: parseGTFSDate(record.start_date),
        endDate: parseGTFSDate(record.end_date)
      }
    });
  }
  console.log(`✓ Imported ${records.length} calendar entries\n`);
}

async function importCalendarDates() {
  const filePath = path.join(GTFS_DIR, 'calendar_dates.txt');
  if (!fs.existsSync(filePath)) {
    console.log('Calendar dates file not found, skipping...\n');
    return;
  }

  console.log('Importing calendar dates...');
  const content = fs.readFileSync(filePath, 'utf-8');
  const records = parse(content, { columns: true, skip_empty_lines: true });

  if (records.length === 0) {
    console.log('No calendar dates to import\n');
    return;
  }

  for (const record of records) {
    await prisma.calendarDate.upsert({
      where: {
        serviceId_date: {
          serviceId: record.service_id,
          date: parseGTFSDate(record.date)
        }
      },
      update: {},
      create: {
        serviceId: record.service_id,
        date: parseGTFSDate(record.date),
        exceptionType: parseInt(record.exception_type)
      }
    });
  }
  console.log(`✓ Imported ${records.length} calendar dates\n`);
}

async function generateRouteGeometries() {
  console.log('Generating route geometries...');

  const routes = await prisma.route.findMany();

  for (const route of routes) {
    // Get trips for this route
    const trips = await prisma.trip.findMany({
      where: { routeId: route.id, shapeId: { not: null } },
      distinct: ['directionId']
    });

    for (const trip of trips) {
      if (!trip.shapeId) continue;

      // Get shape points
      const shapePoints = await prisma.shape.findMany({
        where: { id: trip.shapeId },
        orderBy: { ptSequence: 'asc' }
      });

      if (shapePoints.length === 0) continue;

      // Encode polyline
      const coordinates: [number, number][] = shapePoints.map(pt => [
        Number(pt.ptLat),
        Number(pt.ptLon)
      ]);
      const encoded = polyline.encode(coordinates);

      // Calculate bounds
      const lats = coordinates.map(c => c[0]);
      const lons = coordinates.map(c => c[1]);
      const bounds = {
        ne: { lat: Math.max(...lats), lng: Math.max(...lons) },
        sw: { lat: Math.min(...lats), lng: Math.min(...lons) }
      };

      // Store geometry
      await prisma.routeGeometry.upsert({
        where: {
          routeId_directionId: {
            routeId: route.id,
            directionId: trip.directionId || 0
          }
        },
        update: {
          encodedPolyline: encoded,
          bounds
        },
        create: {
          routeId: route.id,
          directionId: trip.directionId || 0,
          encodedPolyline: encoded,
          bounds
        }
      });
    }
  }

  console.log(`✓ Generated geometries for ${routes.length} routes\n`);
}

function parseGTFSDate(dateStr: string): Date {
  // GTFS dates are in YYYYMMDD format
  const year = parseInt(dateStr.substring(0, 4));
  const month = parseInt(dateStr.substring(4, 6)) - 1;
  const day = parseInt(dateStr.substring(6, 8));
  return new Date(year, month, day);
}

// Run the import
importGTFS();
