// This file defines the routes for the backend API. 
import { Router } from 'express';
import { getRoutes } from '../services/routesService';
import { supabase } from '../config/supabaseClient';

const router = Router();

// GET /api/routes - Fetch all routes
router.get('/routes', async (req, res) => {
    try {
        const routes = await getRoutes();
        res.json(routes);
    } catch (error) {
        res.status(500).json({ error: 'Failed to fetch routes' });
    }
});

// GET /api/trips?id=123 - fetch trip_id, and shape_id to connect routes and shapes
router.get('/trips', async (req, res) => {
    const routeId = req.query.id;

    if (!routeId) {
        return res.status(400).json({ error: 'Route ID is required' });
    }
    
    const { data, error } = await supabase
        .schema('gtfs')
        .from('trips')
        .select('trip_id, shape_id')
        .eq('route_id', routeId);
    
    if (error) {
         console.error('Error fetching trips:', error);
        return res.status(500).json({ error: 'Failed to fetch trips' });
    }

    res.json(data);
});

// GET /api/shapes/shape_id - fetch shape points for a given shape_id to form route lines
router.get('/shapes/:shape_id', async (req, res) => {
    const shapeId = req.params.shape_id;

    if (!shapeId) {
        return res.status(400).json({ error: 'Shape ID is required' });
    }

    const { data, error } = await supabase
        .schema('gtfs')
        .from('shapes')
        .select('shape_pt_lat, shape_pt_lon, shape_pt_sequence')
        .eq('shape_id', shapeId)
        .order('shape_pt_sequence', { ascending: true });
    
    if (error) {
        console.error('Error fetching shapes:', error);
        return res.status(500).json({ error: 'Failed to fetch shapes' });
    }

    //map the data to an array of lat/lon points
    const coordinates = data.map((point) => ({
        latitude: point.shape_pt_lat,
        longitude: point.shape_pt_lon,
    }));

    res.json(coordinates);
});

// GET /api/route-lines - fetch all route lines with their corresponding shape points
router.get('/route-lines', async (req, res) => {
    try {
        // Fetch all routes
        const routes = await getRoutes();

        // For each route, fetch the corresponding trips and shapes
        const routeLines = await Promise.all(routes.map(async (route) => {
            const { data: trips, error: tripsError } = await supabase
                .schema('gtfs')
                .from('trips')
                .select('trip_id, shape_id')
                .eq('route_id', route.route_id)
                .limit(1); // We only need one trip to get the shape_id

            if (tripsError || !trips || trips.length === 0) {
                return null; // Skip routes without trips or with errors
            }

            const shapeId = trips[0].shape_id;

            // Fetch shape points for the shape_id
            const { data: shapePoints, error: shapeError } = await supabase
                .schema('gtfs')
                .from('shapes')
                .select('shape_pt_lat, shape_pt_lon, shape_pt_sequence')
                .eq('shape_id', shapeId)
                .order('shape_pt_sequence', { ascending: true });

            if (shapeError || !shapePoints) {
                return null; // Skip if there's an error fetching shape points
            }

            // Map shape points to an array of lat/lon coordinates
            const coordinates = shapePoints.map((point) => ({
                latitude: point.shape_pt_lat,
                longitude: point.shape_pt_lon,
            }));

            return {
                route_id: route.route_id,
                route_name: route.route_long_name,
                coordinates,
            };
        }));

        // Filter out any null entries (routes that had errors or no trips)
        const validRouteLines = routeLines.filter(line => line !== null);

        res.json(validRouteLines);
    } catch (error) {
        console.error('Error fetching route lines:', error);
        res.status(500).json({ error: 'Failed to fetch route lines' });
    }
});


export default router;