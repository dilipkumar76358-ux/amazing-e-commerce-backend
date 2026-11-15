-- Phase 4: Full-Text Search and Trigram Migration
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'products' 
          AND column_name = 'search_vector'
    ) THEN
        ALTER TABLE public.products
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'C')
        ) STORED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_products_search_vector ON public.products USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON public.products USING GIN(name gin_trgm_ops);
