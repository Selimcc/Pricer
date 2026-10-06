import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { api } from "../api";
import { distance } from "../format";
import { openDirections } from "../maps";
import { useApp } from "../state";
import { colors, radius, space, type } from "../theme";
import type { StoreDetail } from "../types";
import { Button, Confidence, EmptyState, ErrorBox, Header, Loading, PriceTag, ProductThumb, PromoSticker, Row, SectionTitle } from "../ui";

export function StoreScreen({ id }: { id: number }) {
  const { pop, push, coords } = useApp();
  const [data, setData] = useState<StoreDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.store(id, coords));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Magasin indisponible.");
    }
  }, [id, coords]);

  useEffect(() => {
    load();
  }, [load]);

  const store = data?.store;
  return (
    <View style={styles.screen}>
      <Header title={store?.chain ?? "Magasin"} subtitle={store ? distance(store.distance_km) : undefined} onBack={pop} />
      <ScrollView contentContainerStyle={styles.body}>
        {error && <ErrorBox message={error} onRetry={load} />}
        {!data && !error && <Loading />}
        {store && (
          <>
            <View style={styles.card}>
              <Text style={type.bodyStrong}>{store.name}</Text>
              <Text style={type.small}>
                {[store.address, [store.postcode, store.city].filter(Boolean).join(" ")].filter(Boolean).join(", ") ||
                  "Adresse non renseignée sur OpenStreetMap"}
              </Text>
              <Button
                label="Itinéraire"
                icon="navigate"
                compact
                style={{ alignSelf: "flex-start", marginTop: space.sm }}
                onPress={() => openDirections(store.latitude, store.longitude, store.name)}
              />
            </View>

            <SectionTitle>Derniers prix relevés</SectionTitle>
            {data.prices.length === 0 ? (
              <EmptyState
                icon="pricetags-outline"
                title="Pas encore de prix ici"
                text="Tu passes dans ce magasin ? Scanne un produit et relève son prix : tu seras le premier."
                action={<Button label="Scanner un produit" icon="scan" onPress={() => push({ name: "scanner", mode: "lookup" })} />}
              />
            ) : (
              <View style={styles.list}>
                {data.prices.map((p) => (
                  <Pressable key={p.observation_id} style={styles.row} onPress={() => push({ name: "product", ean: p.product.ean })}>
                    <ProductThumb uri={p.product.image_url} size={44} />
                    <View style={{ flex: 1, gap: 3 }}>
                      <Text style={type.bodyStrong} numberOfLines={1}>{p.product.name}</Text>
                      <Row style={{ gap: space.sm }}>
                        <Text style={type.tiny}>{p.freshness_label}</Text>
                        <Confidence level={p.confidence_level} showLabel={false} />
                        {p.is_promotion && <PromoSticker label="Promo" small />}
                      </Row>
                    </View>
                    <PriceTag value={p.price} size="md" />
                  </Pressable>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: space.lg, paddingBottom: space.xxl },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: space.lg, gap: 2 },
  list: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
});
