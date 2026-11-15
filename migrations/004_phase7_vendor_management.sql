-- Migration: Phase 7 Vendor Management & Shipments
-- Creates shipments table and helpful indexes for tenant-isolated vendor queries

CREATE TABLE IF NOT EXISTS public.shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_suborder_id UUID NOT NULL REFERENCES public.vendor_suborders(id) ON DELETE CASCADE,
    carrier VARCHAR(100) NOT NULL,
    tracking_number VARCHAR(120) NOT NULL,
    shipment_status VARCHAR(50) DEFAULT 'in_transit' CHECK (shipment_status IN ('pending', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned')),
    shipped_at TIMESTAMPTZ DEFAULT NOW(),
    estimated_delivery TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shipments_suborder ON public.shipments(vendor_suborder_id);
CREATE INDEX IF NOT EXISTS idx_vendors_owner ON public.vendors(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_vendors_slug ON public.vendors(store_slug);
CREATE INDEX IF NOT EXISTS idx_suborders_fulfillment ON public.vendor_suborders(vendor_id, fulfillment_status);

