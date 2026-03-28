// This file defines the routes for the backend API. 
import { Router } from 'express';
import { getRoutes } from '../services/routesService';

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

export default router;