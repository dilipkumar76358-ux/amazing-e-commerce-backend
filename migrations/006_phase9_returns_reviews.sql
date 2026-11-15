-- Migration: Phase 9 Post-Order Lifecycle, Tracking, Returns & Customer Reviews
-- Implements: public.returns, public.refunds, public.reviews, and automatic rating recalculation trigger

-- ============================================================================
-- 1. RETURNS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES public.order_items(id) ON DELETE CASCADE,
    customer_user_id UUID NOT NULL REFERENCES public.profiles(id),
    vendor_id UUID NOT NULL REFERENCES public.vendors(id),
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    reason VARCHAR(50) NOT NULL CHECK (reason IN ('defective', 'wrong_item', 'not_as_described', 'size_issue', 'arrived_late', 'other')),
    description TEXT,
    evidence_urls TEXT[] DEFAULT '{}',
    return_status VARCHAR(30) DEFAULT 'requested' CHECK (return_status IN ('requested', 'approved', 'rejected', 'in_transit', 'received', 'refunded', 'cancelled')),
    refund_amount NUMERIC(12,2) DEFAULT 0.00,
    refund_id VARCHAR(100),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. REFUNDS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id UUID REFERENCES public.returns(id) ON DELETE SET NULL,
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    gateway_refund_id VARCHAR(100),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(10) DEFAULT 'INR',
    status VARCHAR(30) DEFAULT 'processed' CHECK (status IN ('initiated', 'processed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. REVIEWS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    customer_user_id UUID NOT NULL REFERENCES public.profiles(id),
    order_id UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title VARCHAR(255),
    comment TEXT,
    images TEXT[] DEFAULT '{}',
    is_verified_purchase BOOLEAN DEFAULT TRUE,
    helpful_votes INT DEFAULT 0 CHECK (helpful_votes >= 0),
    review_status VARCHAR(30) DEFAULT 'approved' CHECK (review_status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 4. RATING RECALCULATION TRIGGER FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION public.recalculate_product_rating()
RETURNS TRIGGER AS $$
DECLARE
    target_prod_id UUID;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_prod_id := OLD.product_id;
    ELSE
        target_prod_id := NEW.product_id;
    END IF;

    UPDATE public.products
    SET average_rating = (
        SELECT ROUND(COALESCE(AVG(rating), 0.00), 2)
        FROM public.reviews
        WHERE product_id = target_prod_id AND review_status = 'approved'
    ),
    review_count = (
        SELECT COUNT(*)
        FROM public.reviews
        WHERE product_id = target_prod_id AND review_status = 'approved'
    )
    WHERE id = target_prod_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS on_review_approved ON public.reviews;
CREATE TRIGGER on_review_approved
    AFTER INSERT OR UPDATE OR DELETE ON public.reviews
    FOR EACH ROW EXECUTE FUNCTION public.recalculate_product_rating();

-- ============================================================================
-- 5. PERFORMANCE INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_returns_order ON public.returns(order_id);
CREATE INDEX IF NOT EXISTS idx_returns_customer ON public.returns(customer_user_id);
CREATE INDEX IF NOT EXISTS idx_returns_vendor ON public.returns(vendor_id);
CREATE INDEX IF NOT EXISTS idx_returns_status ON public.returns(return_status);
CREATE INDEX IF NOT EXISTS idx_refunds_order ON public.refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON public.reviews(product_id, review_status);
CREATE INDEX IF NOT EXISTS idx_reviews_customer ON public.reviews(customer_user_id);

-- ============================================================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
ALTER TABLE public.returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    -- Public approved reviews are viewable by anyone
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public approved reviews viewable by everyone') THEN
        CREATE POLICY "Public approved reviews viewable by everyone"
        ON public.reviews FOR SELECT
        USING (review_status = 'approved');
    END IF;

    -- Customers can view their own returns
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Customers view own returns') THEN
        CREATE POLICY "Customers view own returns"
        ON public.returns FOR SELECT
        USING (auth.uid() = customer_user_id);
    END IF;

    -- Customers can initiate returns
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Customers initiate own returns') THEN
        CREATE POLICY "Customers initiate own returns"
        ON public.returns FOR INSERT
        WITH CHECK (auth.uid() = customer_user_id);
    END IF;
END $$;

