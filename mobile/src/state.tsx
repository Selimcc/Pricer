import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { getBaseUrl, setBaseUrl } from "./api";
import { DEMO_COORDS, FORCE_DEMO_LOCATION } from "./config";
import type { Coords, Product } from "./types";

export type Tab = "home" | "list" | "stores" | "me";

export type Route =
  | { name: "scanner"; mode: "lookup" | "list" }
  | { name: "product"; ean: string }
  | { name: "store"; id: number }
  | { name: "createProduct"; ean: string }
  | { name: "receipt"; id?: number };

export type LocationMode = "pending" | "gps" | "demo" | "denied";

type Toast = { id: number; message: string; kind: "info" | "success" | "error" };

type AppState = {
  ready: boolean;
  userId: string;
  coords: Coords;
  locationMode: LocationMode;
  refreshLocation: () => Promise<Coords>;
  useDemoLocation: boolean;
  serverUrl: string;
  setServerUrl: (url: string | null) => void;
  setUseDemoLocation: (v: boolean) => void;

  tab: Tab;
  setTab: (t: Tab) => void;
  stack: Route[];
  push: (r: Route) => void;
  pop: () => void;
  replace: (r: Route) => void;

  toast: Toast | null;
  showToast: (message: string, kind?: Toast["kind"]) => void;

  recent: Product[];
  rememberProduct: (p: Product) => void;

  listVersion: number;
  bumpList: () => void;
};

const Ctx = createContext<AppState | null>(null);

const KEYS = { user: "pricer.userId", recent: "pricer.recent", demo: "pricer.demoLocation", server: "pricer.serverUrl" };

const newUserId = () => `u-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [userId, setUserId] = useState("");
  const [coords, setCoords] = useState<Coords>(DEMO_COORDS);
  const [locationMode, setLocationMode] = useState<LocationMode>("pending");
  const [useDemoLocation, setDemo] = useState(FORCE_DEMO_LOCATION);
  const [tab, setTab] = useState<Tab>("home");
  const [serverUrl, setServer] = useState(getBaseUrl());
  const [stack, setStack] = useState<Route[]>([]);
  const [toast, setToast] = useState<Toast | null>(null);
  const [recent, setRecent] = useState<Product[]>([]);
  const [listVersion, setListVersion] = useState(0);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Identité anonyme de l'appareil + préférences
  useEffect(() => {
    (async () => {
      try {
        let id = await AsyncStorage.getItem(KEYS.user);
        if (!id) {
          id = newUserId();
          await AsyncStorage.setItem(KEYS.user, id);
        }
        setUserId(id);
        const stored = await AsyncStorage.getItem(KEYS.recent);
        if (stored) setRecent(JSON.parse(stored));
        if (!FORCE_DEMO_LOCATION) setDemo((await AsyncStorage.getItem(KEYS.demo)) === "true");
        const server = await AsyncStorage.getItem(KEYS.server);
        if (server) {
          setBaseUrl(server);
          setServer(getBaseUrl());
        }
      } catch {
        setUserId(newUserId());
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const refreshLocation = useCallback(async (): Promise<Coords> => {
    if (useDemoLocation) {
      setCoords(DEMO_COORDS);
      setLocationMode("demo");
      return DEMO_COORDS;
    }
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") {
        setCoords(DEMO_COORDS);
        setLocationMode("denied");
        return DEMO_COORDS;
      }
      const last = await Location.getLastKnownPositionAsync({ maxAge: 120000 });
      if (last) {
        setCoords({ latitude: last.coords.latitude, longitude: last.coords.longitude });
        setLocationMode("gps");
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const c = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
      setCoords(c);
      setLocationMode("gps");
      return c;
    } catch {
      setLocationMode((m) => (m === "gps" ? m : "denied"));
      return coords;
    }
  }, [useDemoLocation, coords]);

  useEffect(() => {
    if (ready) refreshLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, useDemoLocation]);

  const setUseDemoLocation = useCallback((v: boolean) => {
    setDemo(v);
    AsyncStorage.setItem(KEYS.demo, v ? "true" : "false").catch(() => {});
  }, []);

  const setServerUrl = useCallback((url: string | null) => {
    setBaseUrl(url);
    setServer(getBaseUrl());
    if (url && url.trim()) AsyncStorage.setItem(KEYS.server, getBaseUrl()).catch(() => {});
    else AsyncStorage.removeItem(KEYS.server).catch(() => {});
  }, []);

  const showToast = useCallback((message: string, kind: Toast["kind"] = "info") => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ id: Date.now(), message, kind });
    toastTimer.current = setTimeout(() => setToast(null), kind === "error" ? 5000 : 3200);
  }, []);

  const rememberProduct = useCallback((p: Product) => {
    setRecent((prev) => {
      const next = [p, ...prev.filter((x) => x.ean !== p.ean)].slice(0, 8);
      AsyncStorage.setItem(KEYS.recent, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const value = useMemo<AppState>(
    () => ({
      ready,
      userId,
      coords,
      locationMode,
      refreshLocation,
      useDemoLocation,
      setUseDemoLocation,
      serverUrl,
      setServerUrl,
      tab,
      setTab: (t) => {
        setStack([]);
        setTab(t);
      },
      stack,
      push: (r) => setStack((s) => [...s, r]),
      pop: () => setStack((s) => s.slice(0, -1)),
      replace: (r) => setStack((s) => [...s.slice(0, -1), r]),
      toast,
      showToast,
      recent,
      rememberProduct,
      listVersion,
      bumpList: () => setListVersion((v) => v + 1),
    }),
    [ready, userId, coords, locationMode, refreshLocation, useDemoLocation, setUseDemoLocation, serverUrl, setServerUrl, tab, stack, toast,
      showToast, recent, rememberProduct, listVersion],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp doit être utilisé dans <AppProvider>");
  return ctx;
}
