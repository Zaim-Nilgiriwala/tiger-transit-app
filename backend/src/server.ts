import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import routes from './routes/routes.js';

//loads environment variables from .env file
dotenv.config();

// Create an Express application
const app = express();

// Middleware to parse json
app.use(cors());
app.use(express.json());

// Use the routes defined in routes.ts
app.use('/api', routes);

// Start the server
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});