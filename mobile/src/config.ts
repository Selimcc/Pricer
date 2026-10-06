export const APP_NAME = "Pricer";

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? "http://192.168.1.100:8000").replace(/\/$/, "");

/** Forcer la position de démo (Paris centre) : EXPO_PUBLIC_DEMO_LOCATION=true */
export const FORCE_DEMO_LOCATION = process.env.EXPO_PUBLIC_DEMO_LOCATION === "true";

export const DEMO_COORDS = { latitude: 48.8566, longitude: 2.3522 };

/** Rayon de recherche des prix autour de l'utilisateur */
export const SEARCH_RADIUS_KM = 10;
/** Rayon des magasins proposés quand on relève un prix */
export const CONTRIBUTE_RADIUS_KM = 3;
