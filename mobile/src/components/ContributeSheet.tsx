import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useMemo, useState } from "react";
import {
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError, api } from "../api";
import { distance, parsePrice, PROMO_TYPES } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { Product, PromotionType, Store } from "../types";
import { Button, Chip, ErrorBox, IconButton, Loading, ProductThumb, Row } from "../ui";
import { ProofCamera } from "./ProofCamera";

const HERE_KM = 0.3;

export function ContributeSheet({
  product,
  visible,
  onClose,
  onDone,
  preferredStoreId,
}: {
  product: Product;
  visible: boolean;
  onClose: () => void;
  onDone: () => void;
  preferredStoreId?: number;
}) {
  const { userId, refreshLocation, locationMode, showToast } = useApp();
  const insets = useSafeAreaInsets();
  const [stores, setStores] = useState<Store[] | null>(null);
  const [storesError, setStoresError] = useState<string | null>(null);
  const [showAllStores, setShowAllStores] = useState(false);
  const [storeId, setStoreId] = useState<number | null>(null);
  const [price, setPrice] = useState("");
  const [promo, setPromo] = useState(false);
  const [promoType, setPromoType] = useState<PromotionType>("sale");
  const [regular, setRegular] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);

  async function loadStores() {
    setStores(null);
    setStoresError(null);
    try {
      const here = await refreshLocation();
      setPosition(here);
      const list = await api.nearbyStores(here);
      setStores(list);
      const preferred = list.find((s) => s.id === preferredStoreId);
      setStoreId(preferred?.id ?? list[0]?.id ?? null);
    } catch (e) {
      setStoresError(e instanceof Error ? e.message : "Magasins indisponibles.");
    }
  }

  useEffect(() => {
    if (visible) {
      setPrice("");
      setPromo(false);
      setRegular("");
      setPhoto(null);
      setError(null);
      setShowAllStores(false);
      loadStores();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const shownStores = useMemo(() => {
    if (!stores) return [];
    if (showAllStores) return stores;
    const first = stores.slice(0, 4);
    const selected = stores.find((s) => s.id === storeId);
    return selected && !first.includes(selected) ? [...first, selected] : first;
  }, [stores, showAllStores, storeId]);

  const parsed = parsePrice(price);
  const parsedRegular = regular ? parsePrice(regular) : null;
  const canPublish = !!parsed && !!storeId && !saving;

  async function publish() {
    if (!parsed || !storeId) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.createObservation({
        ean: product.ean,
        store_id: storeId,
        price: parsed,
        user_id: userId,
        latitude: locationMode === "gps" ? position?.latitude : undefined,
        longitude: locationMode === "gps" ? position?.longitude : undefined,
        is_promotion: promo,
        promotion_type: promo ? promoType : null,
        regular_price: promo ? parsedRegular : null,
      });
      let message = result.message;
      if (photo) {
        try {
          await api.uploadProof(result.id, userId, photo);
          message = result.flagged ? result.message : "Merci ! Ton prix et sa photo sont en ligne.";
        } catch {
          message = "Prix publié, mais la photo n'a pas pu être envoyée.";
        }
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      showToast(message, result.flagged ? "info" : "success");
      onDone();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Le prix n'a pas pu être publié.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <KeyboardAvoidingView style={styles.sheet} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={[styles.head, Platform.OS === "android" && { paddingTop: insets.top + space.md }]}>
          <ProductThumb uri={product.image_url} size={44} />
          <View style={{ flex: 1 }}>
            <Text style={type.heading}>Relever un prix</Text>
            <Text style={type.small} numberOfLines={1}>
              {product.name}
              {product.quantity ? ` · ${product.quantity}` : ""}
            </Text>
          </View>
          <IconButton icon="close" label="Fermer" onPress={onClose} />
        </View>

        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>Dans quel magasin ?</Text>
          {storesError ? (
            <ErrorBox message={storesError} onRetry={loadStores} />
          ) : !stores ? (
            <Loading text="Recherche des magasins autour de toi…" />
          ) : stores.length === 0 ? (
            <Text style={type.small}>
              Aucun magasin connu à moins de 3 km. Rapproche-toi du magasin ou vérifie ta position.
            </Text>
          ) : (
            <View style={styles.storeList}>
              {shownStores.map((s) => {
                const selected = s.id === storeId;
                const here = (s.distance_km ?? 99) <= HERE_KM && locationMode === "gps";
                return (
                  <Pressable
                    key={s.id}
                    onPress={() => setStoreId(s.id)}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: selected }}
                    style={[styles.storeRow, selected && styles.storeRowSelected]}
                  >
                    <Ionicons
                      name={selected ? "radio-button-on" : "radio-button-off"}
                      size={22}
                      color={selected ? colors.navy : colors.muted}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={type.bodyStrong} numberOfLines={1}>
                        {s.chain}
                      </Text>
                      <Text style={type.tiny} numberOfLines={1}>
                        {s.name !== s.chain ? `${s.name} · ` : ""}
                        {distance(s.distance_km)}
                      </Text>
                    </View>
                    {here && (
                      <View style={styles.hereBadge}>
                        <Text style={styles.hereText}>Tu es ici</Text>
                      </View>
                    )}
                  </Pressable>
                );
              })}
              {stores.length > shownStores.length && (
                <Button label={`Voir les ${stores.length} magasins`} variant="ghost" compact onPress={() => setShowAllStores(true)} />
              )}
            </View>
          )}

          <Text style={styles.label}>Prix affiché</Text>
          <View style={[styles.priceBox, promo && { backgroundColor: colors.promo }]}>
            <TextInput
              value={price}
              onChangeText={setPrice}
              placeholder="0,00"
              placeholderTextColor={promo ? "#8C7A2E" : "#AAB2C3"}
              keyboardType="decimal-pad"
              style={[styles.priceInput, promo && { color: colors.promoInk }]}
              maxLength={6}
              accessibilityLabel="Prix affiché en euros"
            />
            <Text style={[styles.euro, promo && { color: colors.promoInk }]}>€</Text>
          </View>
          {price.length > 0 && !parsed && <Text style={[type.tiny, { color: colors.bad }]}>Écris un prix comme 4,19</Text>}

          <Row style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={type.bodyStrong}>C'est une promotion</Text>
              <Text style={type.tiny}>Fidélité, lot, 2+1, date courte…</Text>
            </View>
            <Switch value={promo} onValueChange={setPromo} trackColor={{ true: colors.navy }} />
          </Row>
          {promo && (
            <View style={{ gap: space.md }}>
              <View style={styles.chips}>
                {PROMO_TYPES.map((t) => (
                  <Chip
                    key={t.value}
                    label={t.label}
                    selected={promoType === t.value}
                    onPress={() => setPromoType(t.value as PromotionType)}
                  />
                ))}
              </View>
              <TextInput
                value={regular}
                onChangeText={setRegular}
                placeholder="Prix sans la promo (facultatif)"
                placeholderTextColor={colors.muted}
                keyboardType="decimal-pad"
                style={styles.input}
              />
            </View>
          )}

          <Text style={styles.label}>Photo de l'étiquette</Text>
          {photo ? (
            <Row style={styles.photoRow}>
              <Image source={{ uri: photo }} style={styles.photo} />
              <View style={{ flex: 1, gap: space.sm }}>
                <Text style={type.small}>Photo prête. Elle rend ton relevé plus fiable.</Text>
                <Row>
                  <Button label="Reprendre" variant="secondary" compact onPress={() => setCameraOpen(true)} />
                  <Button label="Retirer" variant="ghost" compact onPress={() => setPhoto(null)} />
                </Row>
              </View>
            </Row>
          ) : (
            <Button
              label="Photographier l'étiquette"
              icon="camera-outline"
              variant="secondary"
              onPress={() => setCameraOpen(true)}
            />
          )}

          {locationMode !== "gps" && (
            <Text style={[type.tiny, { marginTop: space.sm }]}>
              Position GPS indisponible : ton relevé sera publié, mais sans la vérification « sur place ».
            </Text>
          )}
          {error && <View style={{ marginTop: space.md }}><ErrorBox message={error} /></View>}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
          <Button label="Publier le prix" icon="checkmark" onPress={publish} disabled={!canPublish} loading={saving} />
        </View>
      </KeyboardAvoidingView>

      <ProofCamera
        visible={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCapture={(uri) => {
          setPhoto(uri);
          setCameraOpen(false);
        }}
      />
    </Modal>
  );
}

const styles = StyleSheet.create({
  sheet: { flex: 1, backgroundColor: colors.bg },
  head: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.surface,
  },
  body: { padding: space.lg, paddingBottom: space.xxl },
  label: { ...type.bodyStrong, marginTop: space.xl, marginBottom: space.sm },
  storeList: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  storeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  storeRowSelected: { backgroundColor: colors.navySoft },
  hereBadge: { backgroundColor: colors.goodSoft, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  hereText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.good },
  priceBox: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    borderWidth: 1,
    borderColor: colors.line,
  },
  priceInput: { flex: 1, minWidth: 0, fontFamily: fonts.displayHeavy, fontSize: 60, color: colors.ink, paddingVertical: space.sm },
  euro: { fontFamily: fonts.display, fontSize: 34, color: colors.ink, marginLeft: space.sm },
  switchRow: { marginTop: space.lg, backgroundColor: colors.surface, borderRadius: radius.lg, padding: space.md },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    fontFamily: fonts.medium,
    fontSize: 16,
    color: colors.ink,
  },
  photoRow: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: space.md, gap: space.md },
  photo: { width: 72, height: 96, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  footer: { padding: space.lg, paddingTop: space.md, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.line },
});
