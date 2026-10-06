import React, { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, View } from "react-native";

import { api } from "../api";
import { API_URL, FORCE_DEMO_LOCATION } from "../config";
import { relativeDate } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { Contributions } from "../types";
import { EmptyState, ErrorBox, Header, Loading, PriceTag, ProductThumb, Row, SectionTitle } from "../ui";

export function ProfileScreen() {
  const { userId, push, useDemoLocation, setUseDemoLocation, locationMode } = useApp();
  const [data, setData] = useState<Contributions | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    setError(null);
    try {
      setData(await api.contributions(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Profil indisponible.");
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={styles.screen}>
      <Header title="Moi" subtitle="Tes contributions à la communauté" />
      <ScrollView contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}>
        {error && <ErrorBox message={error} onRetry={load} />}
        {!data && !error && <Loading />}
        {data && (
          <>
            <View style={styles.level}>
              <Text style={styles.levelName}>{data.level.name}</Text>
              {data.level.next_name ? (
                <>
                  <View style={styles.bar}>
                    <View style={[styles.barFill, { width: `${Math.max(4, data.level.progress * 100)}%` }]} />
                  </View>
                  <Text style={styles.levelText}>
                    Encore {Math.max(0, (data.level.next_at ?? 0) - data.score)} point{(data.level.next_at ?? 0) - data.score > 1 ? "s" : ""}{" "}
                    pour devenir {data.level.next_name}. Un prix relevé = 1 point, une photo = 1 point, un produit ajouté au catalogue = 2 points.
                  </Text>
                </>
              ) : (
                <Text style={styles.levelText}>Le plus haut niveau. Merci pour tout ce que tu partages.</Text>
              )}
            </View>

            <View style={styles.stats}>
              <Stat value={data.price_count} label={data.price_count > 1 ? "prix relevés" : "prix relevé"} />
              <Stat value={data.confirmations_received} label={data.confirmations_received > 1 ? "confirmations reçues" : "confirmation reçue"} />
              <Stat value={data.store_count} label={data.store_count > 1 ? "magasins" : "magasin"} />
            </View>

            {data.products_added + data.photos_added > 0 && (
              <Text style={[type.small, { marginTop: space.md }]}>
                Catalogue : {data.products_added} produit{data.products_added > 1 ? "s" : ""} ajouté
                {data.products_added > 1 ? "s" : ""}, {data.photos_added} photo{data.photos_added > 1 ? "s" : ""} de produit.
              </Text>
            )}

            <SectionTitle>Tes derniers relevés</SectionTitle>
            {data.recent.length === 0 ? (
              <EmptyState
                icon="pricetag-outline"
                title="Aucun relevé pour l'instant"
                text="Scanne un produit en magasin puis appuie sur « Relever un prix ». C'est ce qui fait vivre l'app."
              />
            ) : (
              <View style={styles.list}>
                {data.recent.map((r) => (
                  <Pressable key={r.id} style={styles.row} onPress={() => push({ name: "product", ean: r.ean })}>
                    <ProductThumb uri={r.image_url} size={40} />
                    <View style={{ flex: 1 }}>
                      <Text style={type.bodyStrong} numberOfLines={1}>{r.product}</Text>
                      <Text style={type.tiny} numberOfLines={1}>
                        {r.chain} · {relativeDate(r.observed_at)}
                        {r.confirmations ? ` · confirmé ${r.confirmations}×` : ""}
                      </Text>
                    </View>
                    <PriceTag value={r.price} size="sm" />
                  </Pressable>
                ))}
              </View>
            )}
          </>
        )}

        <SectionTitle>Réglages</SectionTitle>
        <View style={styles.list}>
          <Row style={styles.setting}>
            <View style={{ flex: 1 }}>
              <Text style={type.bodyStrong}>Position de démo</Text>
              <Text style={type.tiny}>
                {FORCE_DEMO_LOCATION
                  ? "Forcée par EXPO_PUBLIC_DEMO_LOCATION."
                  : "Fait comme si tu étais à Paris centre, pour tester sans te déplacer."}
              </Text>
            </View>
            <Switch
              value={useDemoLocation}
              onValueChange={setUseDemoLocation}
              disabled={FORCE_DEMO_LOCATION}
              trackColor={{ true: colors.navy }}
            />
          </Row>
          <View style={styles.setting}>
            <Text style={type.bodyStrong}>Localisation</Text>
            <Text style={type.tiny}>
              {locationMode === "gps" ? "Active" : locationMode === "denied" ? "Refusée ou indisponible" : locationMode === "demo" ? "Démo" : "En cours"}
            </Text>
          </View>
          <View style={styles.setting}>
            <Text style={type.bodyStrong}>Serveur</Text>
            <Text style={type.tiny}>{API_URL}</Text>
          </View>
          <View style={[styles.setting, { borderBottomWidth: 0 }]}>
            <Text style={type.bodyStrong}>Identifiant anonyme</Text>
            <Text style={type.tiny}>{userId}. Aucun compte, aucune donnée personnelle.</Text>
          </View>
        </View>
        <Text style={[type.tiny, { marginTop: space.lg }]}>
          Prix : communauté Pricer et Open Prices (Open Food Facts). Magasins : © contributeurs OpenStreetMap. Données sous
          licence ODbL.
        </Text>
      </ScrollView>
    </View>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={type.tiny}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: space.lg, paddingBottom: space.xxl },
  level: { backgroundColor: colors.navy, borderRadius: radius.lg, padding: space.lg, gap: space.sm },
  levelName: { fontFamily: fonts.displayHeavy, fontSize: 32, color: colors.promo },
  levelText: { fontFamily: fonts.medium, fontSize: 14, lineHeight: 19, color: "#C5CEE0" },
  bar: { height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.15)", overflow: "hidden" },
  barFill: { height: "100%", backgroundColor: colors.promo },
  stats: { flexDirection: "row", gap: space.sm, marginTop: space.md },
  stat: { flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, padding: space.md, gap: 2 },
  statValue: { fontFamily: fonts.displayHeavy, fontSize: 30, color: colors.ink },
  list: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  setting: { padding: space.lg, gap: 2, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line },
});
