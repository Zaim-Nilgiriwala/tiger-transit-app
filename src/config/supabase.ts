/**
 * Supabase Client Singleton
 *
 * Initializes the Supabase client with Realtime configuration for
 * receiving live vehicle position updates via WebSocket.
 *
 * URL polyfill MUST be imported first for React Native compatibility.
 */
import 'react-native-url-polyfill/auto';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    '[Supabase] Missing EXPO_PUBLIC_SUPABASE_URL or EXPO_PUBLIC_SUPABASE_ANON_KEY. ' +
      'Supabase client disabled — using ETASpot direct polling instead.',
  );
}

// Use a placeholder URL when credentials are missing to prevent crash.
// The Supabase client won't be used while ETASpot polling is active.
export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-key',
  {
    realtime: {
      params: {
        eventsPerSecond: 10,
      },
    },
  },
);
