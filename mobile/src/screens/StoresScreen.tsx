import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { api } from "../api";
import { distance, relativeDate } from "../format";
import { useApp } from "../state";
import { colors, radius, space, type } from "../theme";
import type { Store } from "../types";
import { Chip, EmptyState, ErrorBox, Header, Loading, Row } from "../ui";

const RADII = [1, 3, 5, 10];

export function StoresScreen() {
  const { coords, push, locationMode } = useApp();
  const [radiusKm, setRadiusKm] = useState(3);
  const [stores, setStores] = useState<Store[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStores(await api.nearbyStores(coords, radiusKm));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Magasins indisponibles.");
    }
  }, [coords, radiusKm]);

  useEffect(() => {
    setStores(null);
    load();
  }, [load]);

  return (
    <View style={styles.screen}>
      <Header
        title="Autour de moi"
        subtitle={locationMode === "gps" ? "Supermarchés et supérettes proches" : "Autour de la position de démo (Paris)"}
      />
      <Row style={styles.radii}>
        {RADII.map((r) => (
          <Chip key={r} label={`${r} km`} selected={r === radiusKm} onPress={() => setRadiusKm(r)} />
        ))}
      </Row>
      {error ? (
        <View style={{ padding: space.lg }}>
          <ErrorBox message={error} onRetry={load} />
        </View>
      ) : !stores ? (
        <Loading text="Chargement des magasins (la première fois peut prendre quelques secondes)…" />
      ) : (
        <FlatList
          data={stores}
          keyExtractor={(s) => String(s.id)}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          ListEmptyComponent={
            <EmptyState
              icon="storefront-outline"
              title="Aucun magasin dans ce rayon"
              text="Élargis le rayon ou vérifie que la localisation est activée."
            />
          }
          renderItem={({ item, index }) => (
            <Pressable
              onPress={() => push({ name: "store", id: item.id })}
              style={[styles.row, index === 0 && styles.first, index === stores.length - 1 && styles.last]}
            >
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={type.bodyStrong} numberOfLines={1}>
                  {item.chain}
                </Text>
                <Text style={type.tiny} numberOfLines={1}>
                  {[...new Set([item.name !== item.chain ? item.name : null, item.address, item.city].filter(Boolean))].join(", ")}
                </Text>
                <Text style={[type.tiny, { color: item.price_count ? colors.good : colors.muted }]}>
                  {item.price_count
                    ? `${item.price_count} prix connu${item.price_count > 1 ? "s" : ""} · dernier ${relativeDate(item.last_price_at!)}`
                    : "Aucun prix relevé pour l'instant"}
                </Text>
              </View>
              <Text style={styles.distance}>{distance(item.distance_km)}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  radii: { paddingHorizontal: space.lg, marginBottom: space.md },
  list: { paddingHorizontal: space.lg, paddingBottom: space.xxl },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    backgroundColor: colors.surface,
    padding: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  first: { borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg },
  last: { borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg, borderBottomWidth: 0 },
  distance: { ...type.small, color: colors.ink },
});
