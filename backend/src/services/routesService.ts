// Fetches routes from the Supabase database
import { supabase } from '../config/supabaseClient';

export async function getRoutes() {
    const { data, error } = await supabase.schema('gtfs').from('routes').select('*');

    if (error) {
        console.error('Error fetching routes:', error);
        throw new Error('Failed to fetch routes');
    }

    return data;
}