import { strFromU8, unzipSync } from 'fflate';
import Papa from 'papaparse';

/* dictates the structure of the unzipped GTFS data, which is a mapping from filename to file contents */
export type GTFSMeta = Record<string, Uint8Array>;

/* Parses GTFS data from a zip file and returns an object mapping filenames to their contents as Uint8Arrays */
export function unzipGtfs(gtfsData: ArrayBuffer | Uint8Array): GTFSMeta {
    const files = gtfsData instanceof Uint8Array ? gtfsData : new Uint8Array(gtfsData);
    const unzipped = unzipSync(files);
    return unzipped;
}

/* Retrieves the text content of a specific file from the unzipped GTFS data */
export function getText(file: GTFSMeta, filename: string): string {
    const data = file[filename];
    if (!data) {
        throw new Error(`File ${filename} not found in GTFS data`);
    }
    return strFromU8(data);
}

/* Parses CSV text into an array of objects, where each object represents a row with column headers as keys */
export function parseCsv(text: string) {
    const res = Papa.parse<Record<string, string>>(text, {
        header: true,
        skipEmptyLines: true,
    });
    return res.data;
}

export type GTFSRoute = {
    route_id: string;
    route_short_name: string;
    route_long_name: string;
    route_color?: string;
};

export function parseRoutes(text: GTFSMeta): GTFSRoute[] {
    const routesText = getText(text, 'routes.txt');
    const rows = parseCsv(routesText);

    const mappedRows = rows.map((r) => ({
        route_id: r.route_id,
        route_short_name: r.route_short_name,
        route_long_name: r.route_long_name,
        route_color: r.route_color,
    }));
    return mappedRows;
} 
