-- Phase 5: Cart and Wishlist Unique Constraints and Indexes
CREATE UNIQUE INDEX IF NOT EXISTS uq_cart_items_cart_variant ON public.cart_items (cart_id, variant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wishlist_items_wishlist_product ON public.wishlist_items (wishlist_id, product_id);
