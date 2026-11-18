-- ============================================================================
-- 007_seed_catalog_data.sql
-- Seed script for Amazing E-Commerce Marketplace (Supabase PostgreSQL)
-- Run this in Supabase SQL Editor (Role: postgres)
-- ============================================================================

-- Step 1: Ensure profiles table allows seed data without auth.users requirement
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_id_fkey;

-- Step 2: Seed Vendors & Profiles
INSERT INTO public.profiles (id, display_name, email, phone, account_status)
VALUES 
('11111111-2222-3333-4444-555555555555', 'Dilip Kumar', 'dilip.kumar@amazing.in', '+916300969503', 'active'),
('55555555-6666-7777-8888-000000000001', 'Apex Electronics Merchant', 'apex.merchant@amazing.in', '+919876543210', 'active'),
('99999999-8888-7777-6666-000000000002', 'StrideStyle Fashion Merchant', 'stridestyle@amazing.in', '+919876543211', 'active')
ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name;

INSERT INTO public.vendors (id, owner_user_id, store_name, store_slug, description, logo_url, application_status, account_status)
VALUES
('55555555-6666-7777-8888-999999999999', '55555555-6666-7777-8888-000000000001', 'Apex Electronics Store', 'apex-electronics', 'Authorized dealer of premium audio, computers, and smart devices.', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=200', 'approved', 'active'),
('99999999-8888-7777-6666-555555555555', '99999999-8888-7777-6666-000000000002', 'StrideStyle Apparel', 'stridestyle-apparel', 'High performance activewear, footwear, and casual lifestyle apparel.', 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=200', 'approved', 'active')
ON CONFLICT (id) DO UPDATE SET store_name = EXCLUDED.store_name;

-- Step 3: Seed Categories
INSERT INTO public.categories (id, parent_id, name, slug, description, image_url, sort_order, is_active)
VALUES
('11111111-aaaa-bbbb-cccc-000000000001', NULL, 'Electronics', 'electronics', 'Smart devices, audio, and personal computers', 'https://images.unsplash.com/photo-1498049794561-7780e7231661?w=600&q=80', 1, TRUE),
('11111111-aaaa-bbbb-cccc-000000000002', '11111111-aaaa-bbbb-cccc-000000000001', 'Audio & Headphones', 'audio-headphones', 'Noise-cancelling wireless headphones and earbuds', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&q=80', 2, TRUE),
('11111111-aaaa-bbbb-cccc-000000000003', '11111111-aaaa-bbbb-cccc-000000000001', 'Mobiles & Accessories', 'mobiles-accessories', 'Latest 5G smartphones and protective covers', 'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&q=80', 3, TRUE),
('11111111-aaaa-bbbb-cccc-000000000004', NULL, 'Fashion & Apparel', 'fashion', 'Men and women ethnic and modern apparel', 'https://images.unsplash.com/photo-1445205170230-053b83016050?w=600&q=80', 4, TRUE),
('11111111-aaaa-bbbb-cccc-000000000005', '11111111-aaaa-bbbb-cccc-000000000001', 'Laptops & Computers', 'laptops-computers', 'Ultrabooks, gaming rigs, and productivity workstations', 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&q=80', 5, TRUE)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Step 4: Seed Brands
INSERT INTO public.brands (id, name, slug, logo_url, is_active)
VALUES
('22222222-bbbb-cccc-dddd-000000000001', 'SonicPulse', 'sonicpulse', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=100', TRUE),
('22222222-bbbb-cccc-dddd-000000000002', 'SwiftBook', 'swiftbook', 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=100', TRUE),
('22222222-bbbb-cccc-dddd-000000000003', 'NovaMobility', 'novamobility', 'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=100', TRUE),
('22222222-bbbb-cccc-dddd-000000000004', 'AeroStride', 'aerostride', 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=100', TRUE),
('22222222-bbbb-cccc-dddd-000000000005', 'ApexExclusive', 'apexexclusive', 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=100', TRUE)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Step 5: Seed Products
INSERT INTO public.products (id, vendor_id, category_id, brand_id, name, slug, description, product_status, average_rating, review_count)
VALUES
(
    '33333333-cccc-dddd-eeee-000000000001',
    '55555555-6666-7777-8888-999999999999',
    '11111111-aaaa-bbbb-cccc-000000000002',
    '22222222-bbbb-cccc-dddd-000000000001',
    'Wireless ANC Bluetooth Over-Ear Headphones (50H Playtime)',
    'wireless-anc-bluetooth-over-ear-headphones',
    'Flagship hybrid active noise cancellation with 40mm dynamic titanium drivers, 50 hours battery life, fast USB-C charge, and ultra-comfortable memory foam ear cushions.',
    'active',
    4.60,
    284
),
(
    '33333333-cccc-dddd-eeee-000000000002',
    '55555555-6666-7777-8888-999999999999',
    '11111111-aaaa-bbbb-cccc-000000000005',
    '22222222-bbbb-cccc-dddd-000000000002',
    'Ultrabook Thin & Light 15.6-inch Laptop Core i7 (16GB RAM, 512GB SSD)',
    'ultrabook-thin-light-15-inch-laptop-core-i7',
    'High-performance Intel Core i7 laptop with backlit keyboard, FHD IPS anti-glare display, Windows 11 Home, and 12-hour all-day battery life.',
    'active',
    4.80,
    512
),
(
    '33333333-cccc-dddd-eeee-000000000003',
    '55555555-6666-7777-8888-999999999999',
    '11111111-aaaa-bbbb-cccc-000000000003',
    '22222222-bbbb-cccc-dddd-000000000003',
    'Nova Pro 5G Smartphone with 108MP Camera (8GB RAM, 128GB Storage)',
    'nova-pro-5g-smartphone-108mp-camera',
    'Blazing fast 5G connectivity, 120Hz Super AMOLED curved display, 108MP OIS triple camera, 67W Turbo charging, and dual stereo Dolby speakers.',
    'active',
    4.50,
    390
),
(
    '33333333-cccc-dddd-eeee-000000000004',
    '99999999-8888-7777-6666-555555555555',
    '11111111-aaaa-bbbb-cccc-000000000004',
    '22222222-bbbb-cccc-dddd-000000000004',
    'Men''s Performance Lightweight Breathable Running Shoes',
    'mens-performance-lightweight-running-shoes',
    'Engineered mesh upper with responsive EVA foam cushioning for endurance running, marathon training, gym workouts, and daily walking comfort.',
    'active',
    4.30,
    142
),
(
    '33333333-cccc-dddd-eeee-000000000005',
    '55555555-6666-7777-8888-999999999999',
    '11111111-aaaa-bbbb-cccc-000000000001',
    '22222222-bbbb-cccc-dddd-000000000005',
    'Exclusive Limited Edition Mechanical Flagship Keyboard',
    'exclusive-limited-edition-keyboard',
    'Ultra rare mechanical flagship keyboard with hot-swappable tactile switches, RGB per-key backlighting, CNC aluminum chassis, and coiled aviator cable.',
    'active',
    4.90,
    58
),
(
    '33333333-cccc-dddd-eeee-000000000006',
    '55555555-6666-7777-8888-999999999999',
    '11111111-aaaa-bbbb-cccc-000000000001',
    '22222222-bbbb-cccc-dddd-000000000001',
    'Smart Watch with AMOLED Display & Bluetooth Calling (IP68 Water Resistant)',
    'smart-watch-amoled-display-bluetooth-calling',
    '1.43-inch Always-On AMOLED screen with Bluetooth calling, heart rate, SpO2 monitor, 110+ sports modes, and 10-day battery standby.',
    'active',
    4.40,
    310
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description;

-- Step 6: Seed Product Variants
INSERT INTO public.product_variants (id, product_id, sku, variant_attributes, selling_price, compare_at_price, weight_grams, is_active)
VALUES
(
    '44444444-dddd-eeee-ffff-000000000001',
    '33333333-cccc-dddd-eeee-000000000001',
    'HP-ANC-BLK',
    '{"color": "Midnight Black"}',
    1999.00,
    4999.00,
    250,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000002',
    '33333333-cccc-dddd-eeee-000000000001',
    'HP-ANC-SLV',
    '{"color": "Lunar Silver"}',
    2199.00,
    5499.00,
    250,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000003',
    '33333333-cccc-dddd-eeee-000000000002',
    'LAP-I7-16-512',
    '{"ram": "16GB", "storage": "512GB SSD"}',
    54990.00,
    72990.00,
    1650,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000004',
    '33333333-cccc-dddd-eeee-000000000003',
    'NOVA-5G-8-128-BLU',
    '{"color": "Glacier Blue", "storage": "128GB"}',
    24999.00,
    29999.00,
    185,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000005',
    '33333333-cccc-dddd-eeee-000000000004',
    'AERO-RUN-RED-9',
    '{"color": "Crimson Red", "size": "UK 9"}',
    1299.00,
    2999.00,
    380,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000006',
    '33333333-cccc-dddd-eeee-000000000005',
    'KB-MECH-LTD-01',
    '{"color": "Cyberpunk Edition"}',
    4999.00,
    7999.00,
    950,
    TRUE
),
(
    '44444444-dddd-eeee-ffff-000000000007',
    '33333333-cccc-dddd-eeee-000000000006',
    'WATCH-AMOLED-BLK',
    '{"color": "Space Black"}',
    2499.00,
    5999.00,
    45,
    TRUE
)
ON CONFLICT (id) DO UPDATE SET selling_price = EXCLUDED.selling_price;

-- Step 7: Seed Product Images
INSERT INTO public.product_images (id, product_id, variant_id, storage_path, alt_text, sort_order)
VALUES
(
    '55555555-eeee-ffff-aaaa-000000000001',
    '33333333-cccc-dddd-eeee-000000000001',
    '44444444-dddd-eeee-ffff-000000000001',
    'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80',
    'Wireless ANC Headphones Front View',
    0
),
(
    '55555555-eeee-ffff-aaaa-000000000002',
    '33333333-cccc-dddd-eeee-000000000002',
    '44444444-dddd-eeee-ffff-000000000003',
    'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500&q=80',
    'Ultrabook Core i7 Laptop Display',
    0
),
(
    '55555555-eeee-ffff-aaaa-000000000003',
    '33333333-cccc-dddd-eeee-000000000003',
    '44444444-dddd-eeee-ffff-000000000004',
    'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=500&q=80',
    'Nova 5G Smartphone Front AMOLED',
    0
),
(
    '55555555-eeee-ffff-aaaa-000000000004',
    '33333333-cccc-dddd-eeee-000000000004',
    '44444444-dddd-eeee-ffff-000000000005',
    'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80',
    'Men Running Shoes Side View',
    0
),
(
    '55555555-eeee-ffff-aaaa-000000000005',
    '33333333-cccc-dddd-eeee-000000000005',
    '44444444-dddd-eeee-ffff-000000000006',
    'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=500&q=80',
    'Mechanical Flagship Keyboard',
    0
),
(
    '55555555-eeee-ffff-aaaa-000000000006',
    '33333333-cccc-dddd-eeee-000000000006',
    '44444444-dddd-eeee-ffff-000000000007',
    'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80',
    'Smart Watch AMOLED Display',
    0
)
ON CONFLICT (id) DO NOTHING;

-- Step 8: Seed Inventory
INSERT INTO public.inventory (id, variant_id, available_quantity, reserved_quantity, low_stock_threshold)
VALUES
('66666666-ffff-aaaa-bbbb-000000000001', '44444444-dddd-eeee-ffff-000000000001', 140, 2, 10),
('66666666-ffff-aaaa-bbbb-000000000002', '44444444-dddd-eeee-ffff-000000000002', 65, 0, 10),
('66666666-ffff-aaaa-bbbb-000000000003', '44444444-dddd-eeee-ffff-000000000003', 45, 1, 5),
('66666666-ffff-aaaa-bbbb-000000000004', '44444444-dddd-eeee-ffff-000000000004', 90, 3, 10),
('66666666-ffff-aaaa-bbbb-000000000005', '44444444-dddd-eeee-ffff-000000000005', 75, 0, 10),
('66666666-ffff-aaaa-bbbb-000000000006', '44444444-dddd-eeee-ffff-000000000006', 15, 0, 3),
('66666666-ffff-aaaa-bbbb-000000000007', '44444444-dddd-eeee-ffff-000000000007', 80, 1, 10)
ON CONFLICT (variant_id) DO UPDATE SET available_quantity = EXCLUDED.available_quantity;

-- Step 9: Seed Coupons (if table exists)
CREATE TABLE IF NOT EXISTS public.coupons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    discount_type VARCHAR(20) DEFAULT 'fixed',
    discount_value NUMERIC(10,2) NOT NULL,
    min_order_amount NUMERIC(10,2) DEFAULT 0.00,
    max_discount_amount NUMERIC(10,2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.coupons (code, description, discount_type, discount_value, min_order_amount, max_discount_amount, is_active)
VALUES
('WELCOME100', 'Flat ₹100 off on your first order', 'fixed', 100.00, 499.00, NULL, TRUE),
('AMAZING50', 'Flat ₹50 off on orders above ₹299', 'fixed', 50.00, 299.00, NULL, TRUE),
('FESTIVE10', '10% instant discount up to ₹500', 'percentage', 10.00, 999.00, 500.00, TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE;

-- ============================================================================
-- Verification Queries (Run these to see populated tables)
-- ============================================================================
SELECT 'Products Count' AS item, COUNT(*) FROM public.products
UNION ALL
SELECT 'Variants Count', COUNT(*) FROM public.product_variants
UNION ALL
SELECT 'Categories Count', COUNT(*) FROM public.categories
UNION ALL
SELECT 'Inventory Units', SUM(available_quantity) FROM public.inventory
UNION ALL
SELECT 'Coupons Count', COUNT(*) FROM public.coupons;
