export type Coords = { latitude: number; longitude: number };

export type Product = {
  id: number;
  ean: string;
  name: string;
  brand?: string | null;
  quantity?: string | null;
  image_url?: string | null;
  quantity_value?: string | number | null;
  quantity_unit?: string | null;
  nutriscore_grade?: string | null;
  source?: string | null;
};

export type ConfidenceLevel = "high" | "medium" | "low";

export type PromotionType = "sale" | "loyalty" | "multi_buy" | "bundle" | "clearance" | "coupon" | "other";

export type PriceRow = {
  observation_id: number;
  store_id: number;
  store_name: string;
  chain: string;
  store_city?: string | null;
  store_latitude: number;
  store_longitude: number;
  price: number;
  regular_price?: number | null;
  unit_price?: number | null;
  unit_price_label?: string | null;
  is_promotion: boolean;
  promotion_type?: PromotionType | null;
  promotion_label?: string | null;
  observed_at: string;
  distance_km?: number | null;
  confirmations: number;
  rejections: number;
  confidence: number;
  confidence_level: ConfidenceLevel;
  freshness_label: string;
  has_proof: boolean;
  proof_image_url?: string | null;
  gps_verified: boolean;
  source: "community" | "open_prices" | "demo" | string;
  source_label: string;
  is_mine: boolean;
  my_vote?: 1 | -1 | null;
  rank: number;
  savings_vs_best: number;
};

export type PriceStats = { min: number; median: number; max: number; count: number; days: number };

export type Comparison = {
  product: Product;
  results: PriceRow[];
  best_price: number | null;
  store_count: number;
  potential_savings: number;
  nearest_store_id: number | null;
  price_stats: PriceStats | null;
  deal: { percent: number; label: string } | null;
  sources: Record<string, number>;
  area: { radius_km: number; stores_in_area: number; osm_import: "imported" | "cached" | "failed" };
};

export type Store = {
  id: number;
  chain: string;
  name: string;
  address?: string | null;
  city?: string | null;
  postcode?: string | null;
  latitude: number;
  longitude: number;
  shop_type?: string | null;
  source?: string;
  distance_km?: number | null;
  price_count?: number | null;
  last_price_at?: string | null;
};

export type StoreDetail = {
  store: Store;
  prices: (PriceRow & { product: Pick<Product, "ean" | "name" | "brand" | "image_url" | "quantity"> })[];
};

export type ListItem = {
  id: number;
  quantity: number;
  checked: boolean;
  added_at: string;
  product: Product;
};

export type BasketStore = {
  store_id: number;
  store_name: string;
  chain: string;
  city?: string | null;
  latitude: number;
  longitude: number;
  distance_km: number;
  covered: number;
  coverage: number;
  known_total: number;
  estimated_total: number;
  extra_vs_best: number;
  missing: { ean: string; name: string }[];
};

export type BasketComparison = {
  stores: BasketStore[];
  total_items: number;
  priced_items: number;
  unpriced: { ean: string; name: string }[];
  split: { total: number; store_count: number } | null;
  max_savings?: number;
};

export type Contributions = {
  user_id: string;
  price_count: number;
  confirmations_received: number;
  votes_cast: number;
  store_count: number;
  proof_count: number;
  score: number;
  level: { name: string; next_name: string | null; next_at: number | null; progress: number };
  recent: {
    id: number;
    ean: string;
    product: string;
    image_url?: string | null;
    chain: string;
    store: string;
    price: number;
    observed_at: string;
    is_promotion: boolean;
    has_proof: boolean;
    confirmations: number;
    rejections: number;
  }[];
};

export type ObservationResult = {
  id: number;
  status: "created" | "updated";
  gps_verified: boolean;
  gps_distance_m: number | null;
  flagged: boolean;
  message: string;
};

export type VoteResult = {
  confirmations: number;
  rejections: number;
  my_vote: 1 | -1;
  disputed: boolean;
  confidence: number;
  confidence_level: ConfidenceLevel;
};

export type RecentObservation = {
  id: number;
  ean: string;
  product: string;
  brand?: string | null;
  image_url?: string | null;
  store: string;
  chain: string;
  city?: string | null;
  price: number;
  promotion?: string | null;
  observed_at: string;
  source: string;
  confidence_level: ConfidenceLevel;
};
