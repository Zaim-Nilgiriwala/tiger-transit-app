import { loadMeta, loadRoutes, saveMeta, saveRoutes } from "./gtfsStorage";


const GTFS_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/gtfs.zip";

async function headGtfs() {
    const response = await fetch(GTFS_URL, { method: 'HEAD' });
    if (!response.ok) {
        throw new Error(`Failed to fetch GTFS metadata: ${response.statusText}`);
    }
    return {
        etag: response.headers.get('etag'),
        lastModified: response.headers.get('last-modified'),
    };
}

async function downloadGtfs() {
    const response = await fetch(GTFS_URL);
    if (!response.ok) {
        throw new Error(`Failed to download GTFS data: ${response.statusText}`);
    }
    return await response.arrayBuffer();
}

export async function updateGtfs() {
    const cachedRoutes = await loadRoutes();
    const cachedMeta = await loadMeta();

    const { etag, lastModified } = await headGtfs();

    const changed = etag !== cachedMeta?.etag || lastModified !== cachedMeta?.lastModified;

    if (!changed && cachedRoutes) {
        return { routes: cachedRoutes, updated: false };
    }

    const gtfsData = await downloadGtfs();

    // Process the GTFS data here (e.g., parse it, update the database, etc.)
    const newRoutes = {
        generatedAt: Date.now(),
        zipSize: gtfsData.byteLength,
        routes: [], // Placeholder for parsed routes
    };

    await saveRoutes(newRoutes);
    await saveMeta({
        etag: etag,
        lastModified: lastModified,
        updatedAt: Date.now(),
    });
    return { routes: newRoutes, updated: true };
}
