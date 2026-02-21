import AsyncStorage from '@react-native-async-storage/async-storage';

const ROUTE_STORAGE_KEY = 'gtfs.routes';
const META_KEY = 'gtfs.meta';

export type GTFStype = {
    etag: string | null;
    lastModified: string | null;
    updatedAt: number | null;
}

export async function loadRoutes() {
    const raw = await AsyncStorage.getItem(ROUTE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
}

export async function saveRoutes(tree: any) {
    await AsyncStorage.setItem(ROUTE_STORAGE_KEY, JSON.stringify(tree));
}

export async function loadMeta() {
    const raw = await AsyncStorage.getItem(META_KEY);
    return raw ? (JSON.parse(raw) as GTFStype) : null;
}

export async function saveMeta(meta: GTFStype) {
    await AsyncStorage.setItem(META_KEY, JSON.stringify(meta));
}