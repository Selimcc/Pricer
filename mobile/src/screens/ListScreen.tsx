import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api } from "../api";
import { distance, money, signedMoney } from "../format";
import { openDirections } from "../maps";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { BasketComparison, ListItem, Product } from "../types";
import { Button, EmptyState, ErrorBox, Header, IconButton, Loading, PriceTag, ProductThumb, Row, SectionTitle } from "../ui";

export function ListScreen() {
  const { userId, coords, push, listVersion, showToast } = useApp();
  const [items, setItems] = useState<ListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [basket, setBasket] = useState<BasketComparison | null>(null);
  const [basketLoading, setBasketLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      setError(null);
      setItems(await api.list(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Liste indisponible.");
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load, listVersion]);

  // Comparaison des magasins dès que la liste (non cochée) change
  const signature = (items ?? []).filter((i) => !i.checked).map((i) => `${i.product.ean}x${i.quantity}`).join(",");
  useEffect(() => {
    if (!signature) {
      setBasket(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      setBasketLoading(true);
      try {
        const b = await api.compareList(userId, coords);
        if (!cancelled) setBasket(b);
      } catch {
        if (!cancelled) setBasket(null);
      } finally {
        if (!cancelled) setBasketLoading(false);
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [signature, coords.latitude, coords.longitude, userId]); // eslint-disable-line react-hooks/exhaustive-deps

  function onQuery(text: string) {
    setQuery(text);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (text.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    searchTimer.current = setTimeout(async () => {
      try {
        setSuggestions(await api.searchProducts(text.trim()));
      } catch {
        setSuggestions([]);
      }
    }, 300);
  }

  async function add(p: Product) {
    setQuery("");
    setSuggestions([]);
    try {
      await api.addToList(userId, p.ean);
      load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Ajout impossible.", "error");
    }
  }

  async function update(item: ListItem, change: { quantity?: number; checked?: boolean }) {
    setItems((list) => list?.map((i) => (i.id === item.id ? { ...i, ...change } : i)) ?? null);
    try {
      if (change.quantity === 0) {
        await api.removeListItem(userId, item.id);
        setItems((list) => list?.filter((i) => i.id !== item.id) ?? null);
      } else {
        await api.updateListItem(userId, item.id, change);
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Modification impossible.", "error");
      load();
    }
  }

  async function clearChecked() {
    try {
      await api.clearChecked(userId);
      load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Action impossible.", "error");
    }
  }

  const todo = (items ?? []).filter((i) => !i.checked);
  const done = (items ?? []).filter((i) => i.checked);

  return (
    <View style={styles.screen}>
      <Header
        title="Ma liste"
        subtitle={items ? `${todo.length} produit${todo.length > 1 ? "s" : ""} à acheter` : undefined}
        right={<IconButton icon="scan" label="Scanner pour ajouter" tone="dark" onPress={() => push({ name: "scanner", mode: "list" })} />}
      />
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
      >
        <View style={styles.search}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            value={query}
            onChangeText={onQuery}
            placeholder="Ajouter un produit déjà scanné…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            accessibilityLabel="Rechercher un produit à ajouter"
          />
        </View>
        {suggestions.length > 0 && (
          <View style={styles.suggestions}>
            {suggestions.slice(0, 6).map((p) => (
              <Pressable key={p.ean} onPress={() => add(p)} style={styles.suggestion}>
                <ProductThumb uri={p.image_url} size={36} />
                <View style={{ flex: 1 }}>
                  <Text style={type.bodyStrong} numberOfLines={1}>{p.name}</Text>
                  <Text style={type.tiny} numberOfLines={1}>{[p.brand, p.quantity].filter(Boolean).join(" · ")}</Text>
                </View>
                <Ionicons name="add-circle" size={24} color={colors.navy} />
              </Pressable>
            ))}
          </View>
        )}
        {query.trim().length >= 2 && suggestions.length === 0 && (
          <Text style={[type.tiny, { marginTop: space.xs }]}>Pas trouvé ? Scanne-le pour l'ajouter.</Text>
        )}

        {error && <View style={{ marginTop: space.lg }}><ErrorBox message={error} onRetry={load} /></View>}
        {!items && !error && <Loading />}

        {items && items.length === 0 && (
          <EmptyState
            icon="cart-outline"
            title="Ta liste est vide"
            text="Scanne les produits de ton placard ou cherche-les ci-dessus. On calcule ensuite le magasin le moins cher pour l'ensemble."
            action={<Button label="Scanner des produits" icon="scan" onPress={() => push({ name: "scanner", mode: "list" })} />}
          />
        )}

        {todo.length > 0 && (
          <View style={[styles.items, { marginTop: space.lg }]}>
            {todo.map((item) => (
              <ItemRow key={item.id} item={item} onChange={(c) => update(item, c)} onOpen={() => push({ name: "product", ean: item.product.ean })} />
            ))}
          </View>
        )}

        {/* Où faire ses courses */}
        {todo.length > 0 && (
          <>
            <SectionTitle>Où faire tes courses</SectionTitle>
            {basketLoading && !basket && <Loading text="Comparaison des magasins…" />}
            {basket && <BasketView basket={basket} />}
          </>
        )}

        {done.length > 0 && (
          <>
            <SectionTitle right={<Button label="Retirer" variant="ghost" compact onPress={clearChecked} />}>
              Dans le chariot
            </SectionTitle>
            <View style={styles.items}>
              {done.map((item) => (
                <ItemRow key={item.id} item={item} onChange={(c) => update(item, c)} onOpen={() => push({ name: "product", ean: item.product.ean })} />
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function ItemRow({
  item,
  onChange,
  onOpen,
}: {
  item: ListItem;
  onChange: (c: { quantity?: number; checked?: boolean }) => void;
  onOpen: () => void;
}) {
  return (
    <View style={styles.item}>
      <Pressable
        onPress={() => onChange({ checked: !item.checked })}
        hitSlop={8}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: item.checked }}
        accessibilityLabel={item.product.name}
      >
        <Ionicons name={item.checked ? "checkbox" : "square-outline"} size={26} color={item.checked ? colors.good : colors.muted} />
      </Pressable>
      <Pressable onPress={onOpen} style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: space.md }}>
        <ProductThumb uri={item.product.image_url} size={40} />
        <View style={{ flex: 1 }}>
          <Text style={[type.bodyStrong, item.checked && styles.checked]} numberOfLines={1}>
            {item.product.name}
          </Text>
          <Text style={type.tiny} numberOfLines={1}>
            {[item.product.brand, item.product.quantity].filter(Boolean).join(" · ")}
          </Text>
        </View>
      </Pressable>
      {!item.checked && (
        <View style={styles.stepper}>
          <Pressable onPress={() => onChange({ quantity: item.quantity - 1 })} hitSlop={6} accessibilityLabel="Diminuer la quantité" style={styles.stepBtn}>
            <Ionicons name={item.quantity === 1 ? "trash-outline" : "remove"} size={16} color={colors.ink} />
          </Pressable>
          <Text style={styles.qty}>{item.quantity}</Text>
          <Pressable onPress={() => onChange({ quantity: Math.min(99, item.quantity + 1) })} hitSlop={6} accessibilityLabel="Augmenter la quantité" style={styles.stepBtn}>
            <Ionicons name="add" size={16} color={colors.ink} />
          </Pressable>
        </View>
      )}
    </View>
  );
}

function BasketView({ basket }: { basket: BasketComparison }) {
  const [best, ...others] = basket.stores;
  if (!best) {
    return (
      <Text style={type.small}>
        Aucun prix connu autour de toi pour ces produits. Relève-les en magasin : ta prochaine liste en profitera.
      </Text>
    );
  }
  const estimated = best.covered < basket.priced_items;
  return (
    <View style={{ gap: space.md }}>
      <View style={styles.bestStore}>
        <Text style={styles.bestKicker}>Le panier le moins cher</Text>
        <Row style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
          <View style={{ flex: 1 }}>
            <Text style={styles.bestChain} numberOfLines={1}>{best.chain}</Text>
            <Text style={styles.bestMeta} numberOfLines={1}>
              {best.store_name !== best.chain ? `${best.store_name} · ` : ""}
              {distance(best.distance_km)}
            </Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            {estimated && <Text style={styles.bestMeta}>environ</Text>}
            <PriceTag value={best.estimated_total} size="lg" tone="white" />
          </View>
        </Row>
        <Text style={styles.bestMeta}>
          Prix connus ici pour {best.covered} produit{best.covered > 1 ? "s" : ""} sur {basket.priced_items}
          {estimated ? " ; les autres sont comptés au prix moyen du secteur." : "."}
        </Text>
        {basket.max_savings ? (
          <Text style={[styles.bestMeta, { color: "#8EE3BE", fontFamily: fonts.semibold }]}>
            Jusqu'à {money(basket.max_savings)} d'économie par rapport au plus cher
          </Text>
        ) : null}
        <Button
          label="Itinéraire"
          icon="navigate"
          variant="secondary"
          compact
          style={{ alignSelf: "flex-start", marginTop: space.sm }}
          onPress={() => openDirections(best.latitude, best.longitude, best.store_name)}
        />
      </View>

      {others.length > 0 && (
        <View style={styles.items}>
          {others.slice(0, 5).map((s) => (
            <View key={s.store_id} style={styles.otherStore}>
              <View style={{ flex: 1 }}>
                <Text style={type.bodyStrong} numberOfLines={1}>{s.chain}</Text>
                <Text style={type.tiny}>
                  {distance(s.distance_km)} · {s.covered}/{basket.priced_items} prix connus
                </Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <PriceTag value={s.estimated_total} size="sm" />
                <Text style={[type.tiny, { color: colors.bad }]}>{signedMoney(s.extra_vs_best)}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {basket.split && basket.split.store_count > 1 && basket.split.total < best.estimated_total - 0.5 && (
        <Text style={type.small}>
          En passant dans {basket.split.store_count} magasins, tu paierais {money(basket.split.total)}.
        </Text>
      )}
      {basket.unpriced.length > 0 && (
        <Text style={type.small}>
          Pas encore de prix autour de toi pour : {basket.unpriced.map((u) => u.name).join(", ")}. Relève-les en magasin !
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: space.lg, paddingBottom: space.xxl },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: space.md,
  },
  searchInput: { flex: 1, paddingVertical: 13, fontFamily: fonts.medium, fontSize: 16, color: colors.ink },
  suggestions: { backgroundColor: colors.surface, borderRadius: radius.md, marginTop: space.xs, overflow: "hidden" },
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  items: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  checked: { textDecorationLine: "line-through", color: colors.muted },
  stepper: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceAlt, borderRadius: radius.pill },
  stepBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  qty: { fontFamily: fonts.display, fontSize: 18, minWidth: 18, textAlign: "center", color: colors.ink },
  bestStore: { backgroundColor: colors.navy, borderRadius: radius.lg, padding: space.lg, gap: space.xs },
  bestKicker: { fontFamily: fonts.medium, fontSize: 14, color: "#AEB9D3" },
  bestChain: { fontFamily: fonts.display, fontSize: 26, color: colors.white },
  bestMeta: { fontFamily: fonts.medium, fontSize: 14, color: "#C5CEE0" },
  otherStore: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
});
