-- Allow entering the schema
GRANT USAGE ON SCHEMA gtfs TO service_role;

-- Allow ONLY reading tables
GRANT SELECT ON ALL TABLES IN SCHEMA gtfs TO service_role;

-- Remove write permissions (just to be safe)
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gtfs FROM service_role;