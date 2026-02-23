-- supabase/migrations/20260221_create_my_table.sql
CREATE TABLE public.my_second_table (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

ALTER TABLE public.my_second_table ENABLE ROW LEVEL SECURITY;