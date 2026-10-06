import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import React, { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { APP_NAME } from "../config";
import { isValidBarcode, relativeDate } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { RecentObservation } from "../types";
import { PriceTag, ProductThumb, PromoSticker, Row, SectionTitle } from "../ui";

export function HomeScreen() {
  const { push, setTab, recent, coords, locationMode, refreshLocation } = useApp();
  const insets = useSafeAreaInsets();
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [place, setPlace] = useState<string | null>(null);
  const [feed, setFeed] = useState<RecentObservation[]>([]);

  useEffect(() => {
    api.recentObservations(6).then(setFeed).catch(() => setFeed([]));
  }, []);

  useEffect(() => {
    if (locationMode !== "gps") {
      setPlace(null);
      return;
    }
    Location.reverseGeocodeAsync(coords)
      .then((r) => setPlace(r[0]?.city || r[0]?.subregion || null))
      .catch(() => setPlace(null));
  }, [coords.latitude, coords.longitude, locationMode]); // eslint-disable-line react-hooks/exhaustive-deps

  function searchCode() {
    const clean = code.replace(/\D/g, "");
    if (!isValidBarcode(clean)) {
      setCodeError("Ce code ne correspond à aucun code-barres. Vérifie les chiffres (13 en général).");
      return;
    }
    setCodeError(null);
    setCode("");
    push({ name: "product", ean: clean });
  }

  const locationText =
    locationMode === "gps"
      ? place ?? "Position trouvée"
      : locationMode === "pending"
        ? "Localisation…"
        : "Position de démo";

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ paddingTop: insets.top + space.md, paddingBottom: space.xxl }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.pad}>
        <Row style={{ justifyContent: "space-between" }}>
          <Text style={styles.brand}>{APP_NAME}</Text>
          <Pressable onPress={refreshLocation} style={styles.place} accessibilityRole="button" accessibilityLabel="Actualiser ma position">
            <Ionicons
              name={locationMode === "gps" ? "location" : "location-outline"}
              size={15}
              color={locationMode === "gps" ? colors.good : colors.muted}
            />
            <Text style={[type.tiny, { color: colors.ink }]} numberOfLines={1}>
              {locationText}
            </Text>
          </Pressable>
        </Row>

        <Text style={styles.lead}>Le vrai prix, dans les magasins autour de toi.</Text>

        {/* Action principale */}
        <Pressable
          onPress={() => push({ name: "scanner", mode: "lookup" })}
          style={({ pressed }) => [styles.scan, pressed && { opacity: 0.92 }]}
          accessibilityRole="button"
          accessibilityLabel="Scanner un produit"
        >
          <View style={styles.barcode}>
            {[3, 1, 2, 1, 3, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1].map((w, i) => (
              <View key={i} style={{ width: w * 2, height: "100%", backgroundColor: i % 2 ? "transparent" : colors.white }} />
            ))}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.scanTitle}>Scanner un produit</Text>
            <Text style={styles.scanSub}>et voir où il est le moins cher</Text>
          </View>
          <Ionicons name="arrow-forward" size={26} color={colors.promo} />
        </Pressable>

        {/* Saisie manuelle */}
        <View style={styles.codeRow}>
          <TextInput
            value={code}
            onChangeText={(t) => {
              setCode(t);
              setCodeError(null);
            }}
            placeholder="Ou tape le code-barres"
            placeholderTextColor={colors.muted}
            keyboardType="number-pad"
            returnKeyType="search"
            onSubmitEditing={searchCode}
            style={styles.codeInput}
            maxLength={14}
            accessibilityLabel="Code-barres"
          />
          <Pressable onPress={searchCode} style={styles.codeGo} accessibilityRole="button" accessibilityLabel="Chercher ce code">
            <Ionicons name="search" size={20} color={colors.white} />
          </Pressable>
        </View>
        {codeError && <Text style={[type.tiny, { color: colors.bad, marginTop: space.xs }]}>{codeError}</Text>}

        {/* Liste */}
        <Pressable onPress={() => setTab("list")} style={styles.listCard} accessibilityRole="button">
          <View style={styles.listIcon}>
            <Ionicons name="cart-outline" size={22} color={colors.ink} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={type.bodyStrong}>Avant de partir faire les courses</Text>
            <Text style={type.small}>Mets tes produits dans ta liste, on te dit dans quel magasin aller.</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        {locationMode !== "gps" && locationMode !== "pending" && (
          <Pressable onPress={() => setTab("me")} style={styles.notice} accessibilityRole="button">
            <Ionicons name="information-circle-outline" size={20} color={colors.inkSoft} />
            <Text style={[type.small, { flex: 1, color: colors.inkSoft }]}>
              Sans ta position, les prix sont calculés autour de Paris centre (démo). Réglages dans l'onglet Moi.
            </Text>
          </Pressable>
        )}
      </View>

      {recent.length > 0 && (
        <>
          <View style={styles.pad}>
            <SectionTitle>Vus récemment</SectionTitle>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.recent}>
            {recent.map((p) => (
              <Pressable key={p.ean} onPress={() => push({ name: "product", ean: p.ean })} style={styles.recentItem}>
                <ProductThumb uri={p.image_url} size={64} />
                <Text style={[type.tiny, { color: colors.ink }]} numberOfLines={2}>
                  {p.name}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        </>
      )}

      {feed.length > 0 && (
        <View style={styles.pad}>
          <SectionTitle>Derniers prix relevés</SectionTitle>
          <View style={styles.feed}>
            {feed.map((o) => (
              <Pressable key={o.id} onPress={() => push({ name: "product", ean: o.ean })} style={styles.feedRow}>
                <ProductThumb uri={o.image_url} size={40} />
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={type.bodyStrong} numberOfLines={1}>{o.product}</Text>
                  <Text style={type.tiny} numberOfLines={1}>
                    {o.chain}
                    {o.city ? `, ${o.city}` : ""} · {relativeDate(o.observed_at)}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end", gap: 2 }}>
                  <PriceTag value={o.price} size="sm" />
                  {o.promotion ? <PromoSticker label="Promo" small /> : null}
                </View>
              </Pressable>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  pad: { paddingHorizontal: space.lg },
  brand: { fontFamily: fonts.displayHeavy, fontSize: 34, color: colors.ink, letterSpacing: -0.5 },
  place: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 6,
    maxWidth: 190,
  },
  lead: { ...type.body, color: colors.inkSoft, marginTop: space.xs, marginBottom: space.xl },
  scan: {
    backgroundColor: colors.navy,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.xl,
    flexDirection: "row",
    alignItems: "center",
    gap: space.lg,
  },
  barcode: { flexDirection: "row", gap: 2, height: 52 },
  scanTitle: { fontFamily: fonts.display, fontSize: 26, lineHeight: 28, color: colors.white },
  scanSub: { fontFamily: fonts.medium, fontSize: 15, color: "#B9C3DA" },
  codeRow: {
    flexDirection: "row",
    marginTop: space.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    overflow: "hidden",
  },
  codeInput: { flex: 1, paddingHorizontal: space.md, paddingVertical: 14, fontFamily: fonts.medium, fontSize: 16, color: colors.ink },
  codeGo: { width: 54, alignItems: "center", justifyContent: "center", backgroundColor: colors.inkSoft },
  listCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    marginTop: space.xl,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  listIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.promo,
    alignItems: "center",
    justifyContent: "center",
  },
  notice: {
    flexDirection: "row",
    gap: space.sm,
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.navySoft,
  },
  recent: { paddingHorizontal: space.lg, gap: space.md },
  feed: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  feedRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  recentItem: { width: 84, gap: space.xs },
});
