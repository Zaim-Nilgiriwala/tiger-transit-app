# Tiger-Transit-App
Thousands of Auburn students rely on campus transit like Tiger Transit, jAUnt, and the Security Shuttle, all tracked through ETA Spot. Our team will build a modern, user-friendly replacement that keeps existing features while fixing bugs and adding quality-of-life improvements.

To start the application, you must run the frontend, backend, and database locally on your device.

To start the database, you must:
1. Open Docker
2. Be in the database directory
3. Run the command `npx supabase start`

Create a .env file in the backend directory that includes SUPABASE_URL and SUPABASE_KEY.
* To find the SUPABASE_URL, start the database, and look for the "Studio" url under "Development Tools".
* To find the SUPABASE_KEY, start the database, run the command `npx supabase status --output json`, and copy the SERVICE_ROLE_KEY.

To start the backend, you must:
1. Be in the backend directory
2. Run the command `npm run dev`

To start the frontend, you must:
1. Be in the mobile directory
2. Run the command `npx expo start`

In [index.tsx](mobile\app\(tabs)\index.tsx) add your IP to the fetch statement in line 15.
