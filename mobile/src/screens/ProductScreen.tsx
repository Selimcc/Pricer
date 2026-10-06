import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useState } from "react";
import { Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError, api, imageUrl } from "../api";
import { ContributeSheet } from "../components/ContributeSheet";
import { ProofCamera } from "../components/ProofCamera";
import { SEARCH_RADIUS_KM } from "../config";
import { distance, money, perUnit, signedMoney } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { Comparison, PriceRow, Product } from "../types";
import {
  Button,
  Confidence,
  EmptyState,
  ErrorBox,
  IconButton,
  Loading,
  Meta,
  Nutriscore,
  PriceTag,
  ProductThumb,
  PromoSticker,
  Row,
  SectionTitle,
} from "../ui";

export function ProductScreen({ ean }: { ean: string }) {
  const { pop, replace, push, coords, userId, rememberProduct, showToast, bumpList, locationMode } = useApp();
  const insets = useSafeAreaInsets();
  const [product, setProduct] = useState<Product | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadingPrices, setLoadingPrices] = useState(false);
  const [contributeOpen, setContributeOpen] = useState(false);
  const [preferredStore, setPreferredStore] = useState<number | undefined>();
  const [expanded, setExpanded] = useState<number | null>(null);
  const [proofFor, setProofFor] = useState<number | null>(null);
  const [addingToList, setAddingToList] = useState(false);

  const loadPrices = useCallback(async () => {
    setLoadingPrices(true);
    try {
      setComparison(await api.comparison(ean, coords, userId));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError("unknown", "Les prix n'ont pas pu être chargés."));
    } finally {
      setLoadingPrices(false);
    }
  }, [ean, coords, userId]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      try {
        const p = await api.product(ean);
        if (cancelled) return;
        setProduct(p);
        rememberProduct(p);
        await loadPrices();
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e : new ApiError("unknown", "Erreur inattendue."));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ean]);

  // La position GPS arrive parfois après l'ouverture : on recharge les prix.
  useEffect(() => {
    if (product) loadPrices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords.latitude, coords.longitude]);

  async function addToList() {
    setAddingToList(true);
    try {
      await api.addToList(userId, ean);
      bumpList();
      Haptics.selectionAsync().catch(() => {});
      showToast("Ajouté à ta liste de courses", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Impossible d'ajouter à la liste.", "error");
    } finally {
      setAddingToList(false);
    }
  }

  async function vote(row: PriceRow, value: 1 | -1) {
    try {
      const r = await api.vote(row.observation_id, userId, value);
      Haptics.selectionAsync().catch(() => {});
      showToast(value === 1 ? "Merci, prix confirmé." : "Merci, c'est noté. Tu peux relever le nouveau prix.", "success");
      if (r.disputed) return loadPrices();
      setComparison((c) =>
        c && {
          ...c,
          results: c.results.map((x) =>
            x.observation_id === row.observation_id
              ? { ...x, confirmations: r.confirmations, rejections: r.rejections, my_vote: r.my_vote,
                  confidence: r.confidence, confidence_level: r.confidence_level }
              : x,
          ),
        },
      );
      if (value === -1) {
        setPreferredStore(row.store_id);
        setContributeOpen(true);
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Ton vote n'a pas pu être envoyé.", "error");
    }
  }

  async function uploadProof(uri: string) {
    const id = proofFor;
    setProofFor(null);
    if (!id) return;
    try {
      await api.uploadProof(id, userId, uri);
      showToast("Photo ajoutée à ton relevé.", "success");
      loadPrices();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "La photo n'a pas pu être envoyée.", "error");
    }
  }

  // --- États sans produit -------------------------------------------------
  if (error && !product) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.topBar}>
          <IconButton icon="chevron-back" label="Retour" onPress={pop} />
        </View>
        {error.code === "product_not_found" ? (
          <EmptyState
            icon="help-circle-outline"
            title="Produit pas encore référencé"
            text={`Le code ${ean} n'est ni dans notre base ni dans Open Food Facts. Ajoute-le en 20 secondes, il servira à tout le monde.`}
            action={<Button label="Ajouter ce produit" icon="add" onPress={() => replace({ name: "createProduct", ean })} />}
          />
        ) : error.code === "invalid_ean" ? (
          <EmptyState
            icon="barcode-outline"
            title="Code-barres illisible"
            text={error.message}
            action={<Button label="Rescanner" icon="scan" onPress={() => replace({ name: "scanner", mode: "lookup" })} />}
          />
        ) : (
          <View style={{ padding: space.lg }}>
            <ErrorBox message={error.message} onRetry={() => replace({ name: "product", ean })} />
          </View>
        )}
      </View>
    );
  }

  if (!product) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.topBar}>
          <IconButton icon="chevron-back" label="Retour" onPress={pop} />
        </View>
        <Loading text="Recherche du produit…" />
      </View>
    );
  }

  const results = comparison?.results ?? [];
  const best = results[0];

  return (
    <View style={styles.screen}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + space.sm, paddingBottom: insets.bottom + 110 }}
        refreshControl={<RefreshControl refreshing={loadingPrices && !!comparison} onRefresh={loadPrices} />}
      >
        <View style={styles.topBar}>
          <IconButton icon="chevron-back" label="Retour" onPress={pop} />
          <IconButton icon="scan" label="Scanner un autre produit" onPress={() => replace({ name: "scanner", mode: "lookup" })} />
        </View>

        {/* Produit */}
        <View style={styles.productHead}>
          <ProductThumb uri={product.image_url} size={84} />
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={styles.productName} numberOfLines={3}>
              {product.name}
            </Text>
            <Text style={type.small} numberOfLines={1}>
              {[product.brand, product.quantity].filter(Boolean).join(" · ") || "Marque inconnue"}
            </Text>
            <Row style={{ gap: space.sm, marginTop: 2 }}>
              <Nutriscore grade={product.nutriscore_grade} />
              <Text style={type.tiny}>EAN {product.ean}</Text>
            </Row>
          </View>
        </View>

        <View style={styles.pad}>
          {!comparison && loadingPrices && <Loading text="Recherche des prix autour de toi…" />}
          {error && comparison === null && !loadingPrices && <ErrorBox message={error.message} onRetry={loadPrices} />}

          {/* Meilleur prix */}
          {best && (
            <View style={styles.best}>
              <Text style={styles.bestLabel}>
                {results.length > 1 ? "Le moins cher autour de toi" : "Seul prix connu autour de toi"}
              </Text>
              <Row style={{ alignItems: "flex-start", justifyContent: "space-between" }}>
                <View style={{ gap: space.xs }}>
                  <View style={best.is_promotion ? styles.bestPromoTag : undefined}>
                    <PriceTag value={best.price} size="xl" tone={best.is_promotion ? "promo" : "white"} />
                  </View>
                  {best.regular_price ? (
                    <Text style={styles.bestSub}>au lieu de {money(best.regular_price)}</Text>
                  ) : null}
                </View>
                {best.is_promotion && <PromoSticker label={best.promotion_label || "Promo"} />}
              </Row>
              <Text style={styles.bestStore} numberOfLines={1}>
                {best.chain}
              </Text>
              <Text style={styles.bestSub} numberOfLines={1}>
                {best.store_name !== best.chain ? `${best.store_name} · ` : ""}
                {distance(best.distance_km)} · relevé {best.freshness_label.toLowerCase()}
              </Text>
              <View style={styles.bestFacts}>
                {best.unit_price ? (
                  <Text style={styles.bestFact}>
                    {perUnit(best.unit_price, best.unit_price_label)}
                  </Text>
                ) : null}
                {comparison?.deal && <Text style={[styles.bestFact, { color: "#8EE3BE" }]}>{comparison.deal.label}</Text>}
                {comparison && comparison.potential_savings > 0 && (
                  <Text style={styles.bestFact}>
                    Jusqu'à {money(comparison.potential_savings)} d'écart entre les magasins
                  </Text>
                )}
              </View>
            </View>
          )}

          {/* Actions */}
          {comparison && (
            <Row style={{ marginTop: space.md }}>
              <Button label="Ma liste" icon="add" variant="secondary" onPress={addToList} loading={addingToList} style={{ flex: 1 }} />
              <Button
                label="Relever un prix"
                icon="pricetag-outline"
                onPress={() => {
                  setPreferredStore(undefined);
                  setContributeOpen(true);
                }}
                style={{ flex: 1.4 }}
              />
            </Row>
          )}

          {/* Aucun prix proche et récent */}
          {comparison && results.length === 0 && (
            <>
              <EmptyState
                icon="storefront-outline"
                title={`Pas encore de prix récent à moins de ${SEARCH_RADIUS_KM} km`}
                text={
                  comparison.area.osm_import === "failed" && comparison.area.stores_in_area === 0
                    ? "La carte des magasins n'a pas pu être chargée (OpenStreetMap). Réessaie dans un moment."
                    : "Personne n'a encore relevé ce produit dans les magasins autour de toi. Tu es en magasin ? Relève le prix affiché : tu seras le premier."
                }
              />
              {comparison.fallback && comparison.fallback.results.length > 0 && (
                <>
                  <SectionTitle>Les prix connus les plus proches</SectionTitle>
                  <Text style={[type.small, { marginBottom: space.sm }]}>
                    À titre indicatif : ces relevés sont plus loin ou plus anciens, le prix a pu changer.
                    {comparison.fallback.price_stats && comparison.fallback.price_stats.count >= 3
                      ? ` Prix habituel en France : ${money(comparison.fallback.price_stats.median)} (${comparison.fallback.price_stats.count} relevés sur un an).`
                      : ""}
                  </Text>
                  <View style={styles.list}>
                    {comparison.fallback.results.map((row) => (
                      <Pressable key={row.observation_id} style={styles.fallbackRow} onPress={() => push({ name: "store", id: row.store_id })}>
                        <View style={{ flex: 1, gap: 3 }}>
                          <Text style={type.bodyStrong} numberOfLines={1}>{row.chain}</Text>
                          <Text style={type.tiny} numberOfLines={1}>
                            {[row.store_city, distance(row.distance_km), row.freshness_label.toLowerCase()].filter(Boolean).join(" · ")}
                          </Text>
                        </View>
                        <PriceTag value={row.price} size="md" tone="muted" />
                      </Pressable>
                    ))}
                  </View>
                </>
              )}
            </>
          )}

          {/* Tous les prix */}
          {results.length > 0 && (
            <>
              <SectionTitle right={<Text style={type.tiny}>{results.length} magasin{results.length > 1 ? "s" : ""}</Text>}>
                Tous les prix
              </SectionTitle>
              <View style={styles.list}>
                {results.map((row, i) => (
                  <PriceLine
                    key={row.observation_id}
                    row={row}
                    first={i === 0}
                    open={expanded === row.observation_id}
                    onToggle={() => setExpanded((x) => (x === row.observation_id ? null : row.observation_id))}
                    onVote={(v) => vote(row, v)}
                    onAddProof={() => setProofFor(row.observation_id)}
                    onOpenStore={() => push({ name: "store", id: row.store_id })}
                  />
                ))}
              </View>
            </>
          )}

          {comparison?.price_stats && comparison.price_stats.count >= 3 && (
            <Text style={[type.small, { marginTop: space.lg }]}>
              Sur {comparison.price_stats.days} jours, ce produit a été vu entre {money(comparison.price_stats.min)} et{" "}
              {money(comparison.price_stats.max)} ({comparison.price_stats.count} relevés).
            </Text>
          )}

          {locationMode !== "gps" && (
            <Text style={[type.tiny, { marginTop: space.lg }]}>
              Prix calculés autour d'une position de démo (Paris centre). Active la localisation pour voir tes magasins.
            </Text>
          )}
          <Text style={[type.tiny, { marginTop: space.lg }]}>
            Prix : communauté Pricer et Open Prices. Produits : Open Food Facts. Magasins : © OpenStreetMap. Données ODbL.
          </Text>
        </View>
      </ScrollView>

      <ContributeSheet
        product={product}
        visible={contributeOpen}
        preferredStoreId={preferredStore}
        onClose={() => setContributeOpen(false)}
        onDone={() => {
          setContributeOpen(false);
          loadPrices();
        }}
      />
      <ProofCamera visible={proofFor !== null} onClose={() => setProofFor(null)} onCapture={uploadProof} />
    </View>
  );
}

function PriceLine({
  row,
  first,
  open,
  onToggle,
  onVote,
  onAddProof,
  onOpenStore,
}: {
  row: PriceRow;
  first: boolean;
  open: boolean;
  onToggle: () => void;
  onVote: (v: 1 | -1) => void;
  onAddProof: () => void;
  onOpenStore: () => void;
}) {
  return (
    <View style={styles.line}>
      <Pressable onPress={onToggle} style={styles.lineMain} accessibilityRole="button" accessibilityState={{ expanded: open }}>
        <View style={{ flex: 1, gap: 3 }}>
          <Row style={{ gap: 6 }}>
            <Text style={type.bodyStrong} numberOfLines={1}>
              {row.chain}
            </Text>
            {row.is_promotion && <PromoSticker label={row.promotion_label || "Promo"} small />}
          </Row>
          <Row style={{ gap: space.md, flexWrap: "wrap" }}>
            <Meta icon="navigate-outline" text={distance(row.distance_km)} />
            <Meta icon="time-outline" text={row.freshness_label} />
            <Confidence level={row.confidence_level} />
          </Row>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <PriceTag value={row.price} size="md" />
          {first ? (
            <Text style={[type.tiny, { color: colors.good }]}>le moins cher</Text>
          ) : (
            <Text style={type.tiny}>{signedMoney(row.savings_vs_best)}</Text>
          )}
        </View>
      </Pressable>

      {open && (
        <View style={styles.lineDetail}>
          <Text style={type.small}>
            {row.store_name}
            {row.store_city ? `, ${row.store_city}` : ""}
          </Text>
          <Row style={{ flexWrap: "wrap", gap: space.md }}>
            <Meta icon="person-outline" text={row.is_mine ? "Ton relevé" : `Source : ${row.source_label}`} />
            {row.gps_verified && <Meta icon="location" color={colors.good} text="Relevé sur place" />}
            {row.has_proof && <Meta icon="image-outline" color={colors.good} text="Photo jointe" />}
            {row.unit_price ? <Meta icon="scale-outline" text={perUnit(row.unit_price, row.unit_price_label)} /> : null}
            <Meta
              icon="thumbs-up-outline"
              text={
                `${row.confirmations} confirmation${row.confirmations > 1 ? "s" : ""}` +
                (row.rejections ? ` · ${row.rejections} contestation${row.rejections > 1 ? "s" : ""}` : "")
              }
            />
          </Row>

          {row.proof_image_url && (
            <Image source={{ uri: imageUrl(row.proof_image_url) }} style={styles.proof} resizeMode="cover" />
          )}

          {row.is_mine ? (
            !row.has_proof && <Button label="Ajouter une photo de l'étiquette" icon="camera-outline" variant="secondary" compact onPress={onAddProof} />
          ) : (
            <>
              <Text style={[type.bodyStrong, { marginTop: space.xs }]}>C'est toujours ce prix en rayon ?</Text>
              <Row>
                <Button
                  label={row.my_vote === 1 ? "Confirmé" : "Oui, c'est ça"}
                  icon={row.my_vote === 1 ? "checkmark-circle" : "checkmark"}
                  variant={row.my_vote === 1 ? "good" : "secondary"}
                  compact
                  onPress={() => onVote(1)}
                  style={{ flex: 1 }}
                />
                <Button
                  label={row.my_vote === -1 ? "Signalé" : "Non, il a changé"}
                  icon="close"
                  variant={row.my_vote === -1 ? "danger" : "secondary"}
                  compact
                  onPress={() => onVote(-1)}
                  style={{ flex: 1 }}
                />
              </Row>
            </>
          )}
          <Pressable onPress={onOpenStore} style={styles.storeLink} accessibilityRole="link">
            <Text style={[type.small, { color: colors.ink, fontFamily: fonts.semibold }]}>Voir le magasin</Text>
            <Ionicons name="chevron-forward" size={16} color={colors.ink} />
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  topBar: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: space.lg, marginBottom: space.md },
  pad: { paddingHorizontal: space.lg },
  productHead: { flexDirection: "row", gap: space.lg, paddingHorizontal: space.lg, marginBottom: space.lg, alignItems: "center" },
  productName: { fontFamily: fonts.display, fontSize: 28, lineHeight: 30, color: colors.ink },

  best: { backgroundColor: colors.navy, borderRadius: radius.lg, padding: space.lg, gap: 2 },
  bestLabel: { fontFamily: fonts.medium, fontSize: 14, color: "#AEB9D3", marginBottom: space.xs },
  bestPromoTag: { backgroundColor: colors.promo, borderRadius: 4, paddingHorizontal: space.sm, alignSelf: "flex-start" },
  bestStore: { fontFamily: fonts.display, fontSize: 24, color: colors.white, marginTop: space.sm },
  bestSub: { fontFamily: fonts.medium, fontSize: 14, color: "#C5CEE0" },
  bestFacts: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.15)",
    gap: 4,
  },
  bestFact: { fontFamily: fonts.semibold, fontSize: 14, color: colors.white },

  list: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  line: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line },
  lineMain: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg },
  lineDetail: { paddingHorizontal: space.lg, paddingBottom: space.lg, gap: space.sm, backgroundColor: colors.surface },
  proof: { width: "100%", height: 180, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  fallbackRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  storeLink: { flexDirection: "row", alignItems: "center", gap: 2, alignSelf: "flex-start", paddingVertical: space.xs },
});
