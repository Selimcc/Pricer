import { API_URL, CONTRIBUTE_RADIUS_KM, SEARCH_RADIUS_KM } from "./config";
import type {
  BasketComparison,
  Comparison,
  Contributions,
  Coords,
  ListItem,
  ObservationResult,
  Product,
  PromotionType,
  RecentObservation,
  Store,
  StoreDetail,
  VoteResult,
} from "./types";

/** Erreur lisible par l'utilisateur, avec un code stable pour l'app. */
export class ApiError extends Error {
  constructor(public code: string, message: string, public status = 0) {
    super(message);
  }
}

const TIMEOUT_MS = 30000; // la 1re recherche dans une zone importe les magasins OSM

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(
      "network",
      `Serveur injoignable (${API_URL}). Vérifie que l'API tourne et que le téléphone est sur le même Wi-Fi que le PC.`,
    );
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      throw new ApiError(detail.code, detail.message, response.status);
    }
    const message = Array.isArray(detail) ? "Certaines informations sont invalides." : detail || "Erreur du serveur.";
    throw new ApiError("http_" + response.status, String(message), response.status);
  }
  return body as T;
}

const qs = (params: Record<string, string | number | undefined | null>) =>
  "?" +
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");

const at = (c: Coords) => ({ latitude: c.latitude.toFixed(5), longitude: c.longitude.toFixed(5) });

export const api = {
  baseUrl: API_URL,

  product: (ean: string) => request<Product>(`/products/${encodeURIComponent(ean)}`),

  createProduct: (data: { ean: string; name: string; brand?: string; quantity?: string }) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(data) }),

  searchProducts: (q: string) => request<Product[]>(`/products/search${qs({ q })}`),

  comparison: (ean: string, coords: Coords, userId: string) =>
    request<Comparison>(
      `/products/${encodeURIComponent(ean)}/comparison${qs({ ...at(coords), radius_km: SEARCH_RADIUS_KM, user_id: userId })}`,
    ),

  nearbyStores: (coords: Coords, radiusKm = CONTRIBUTE_RADIUS_KM) =>
    request<Store[]>(`/stores/nearby${qs({ ...at(coords), radius_km: radiusKm })}`),

  store: (id: number, coords: Coords) => request<StoreDetail>(`/stores/${id}${qs(at(coords))}`),

  createObservation: (data: {
    ean: string;
    store_id: number;
    price: string;
    user_id: string;
    latitude?: number;
    longitude?: number;
    is_promotion: boolean;
    promotion_type?: PromotionType | null;
    regular_price?: string | null;
  }) => request<ObservationResult>("/observations", { method: "POST", body: JSON.stringify(data) }),

  uploadProof: (observationId: number, userId: string, photoUri: string) => {
    const form = new FormData();
    form.append("user_id", userId);
    // React Native accepte { uri, name, type } comme fichier
    form.append("file", { uri: photoUri, name: "proof.jpg", type: "image/jpeg" } as unknown as Blob);
    return request<{ proof_image_url: string }>(`/observations/${observationId}/proof`, { method: "POST", body: form });
  },

  vote: (observationId: number, userId: string, vote: 1 | -1) =>
    request<VoteResult>(`/observations/${observationId}/vote`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, vote }),
    }),

  list: (userId: string) => request<ListItem[]>(`/users/${userId}/list`),

  addToList: (userId: string, ean: string, quantity = 1) =>
    request<ListItem>(`/users/${userId}/list`, { method: "POST", body: JSON.stringify({ ean, quantity }) }),

  updateListItem: (userId: string, id: number, data: { quantity?: number; checked?: boolean }) =>
    request<ListItem>(`/users/${userId}/list/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  removeListItem: (userId: string, id: number) =>
    request<void>(`/users/${userId}/list/${id}`, { method: "DELETE" }),

  clearChecked: (userId: string) => request<void>(`/users/${userId}/list`, { method: "DELETE" }),

  compareList: (userId: string, coords: Coords) =>
    request<BasketComparison>(`/users/${userId}/list/comparison${qs({ ...at(coords), radius_km: SEARCH_RADIUS_KM })}`),

  recentObservations: (limit = 6) => request<RecentObservation[]>(`/observations/recent${qs({ limit })}`),

  contributions: (userId: string) => request<Contributions>(`/users/${userId}/contributions`),
};

/** URL absolue d'une image (les preuves locales sont servies par l'API sous /uploads). */
export const imageUrl = (url?: string | null) => (url && url.startsWith("/") ? `${API_URL}${url}` : url ?? undefined);
