import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError, api } from "../api";
import { ProductPicker } from "../components/ProductPicker";
import { ProofCamera } from "../components/ProofCamera";
import { distance, money } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { Receipt, ReceiptLine, Store } from "../types";
import { Button, EmptyState, ErrorBox, Header, IconButton, Loading, PriceTag, ProductThumb, Row } from "../ui";

export function ReceiptScreen({ id }: { id?: number }) {
  const { pop, push, replace, userId, coords, locationMode, refreshLocation, showToast } = useApp();
  const insets = useSafeAreaInsets();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [cameraOpen, setCameraOpen] = useState(!id);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState<ReceiptLine | null>(null);
  const [storePicker, setStorePicker] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (id) api.receipt(id, userId).then(setReceipt).catch((e) => setError(e.message));
  }, [id, userId]);

  async function read(uri: string) {
    setCameraOpen(false);
    setReading(true);
    setError(null);
    try {
      const here = locationMode === "gps" ? await refreshLocation() : undefined;
      const created = await api.uploadReceipt(userId, uri, here);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      // L'identifiant passe dans la route : on retrouve le ticket après un détour (création de produit…)
      replace({ name: "receipt", id: created.id });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Le ticket n'a pas pu être lu.");
    } finally {
      setReading(false);
    }
  }

  async function updateLine(line: ReceiptLine, data: { ean?: string; clear_product?: boolean; status?: "pending" | "ignored" }) {
    if (!receipt) return;
    try {
      setReceipt(await api.updateReceiptLine(receipt.id, line.id, userId, data));
    } catch (e) {
      if (e instanceof ApiError && e.code === "product_not_found" && data.ean) {
        showToast("Produit inconnu : ajoute-le, puis associe-le à la ligne.", "info");
        push({ name: "createProduct", ean: data.ean });
        return;
      }
      showToast(e instanceof Error ? e.message : "Modification impossible.", "error");
    }
  }

  async function chooseStore(store: Store) {
    setStorePicker(false);
    if (!receipt) return;
    try {
      setReceipt(await api.updateReceipt(receipt.id, userId, { store_id: store.id }));
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Magasin non enregistré.", "error");
    }
  }

  async function publish() {
    if (!receipt) return;
    setPublishing(true);
    try {
      const r = await api.publishReceipt(receipt.id, userId);
      setReceipt(r);
      setDone(r.message ?? "Prix publiés.");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Publication impossible.", "error");
    } finally {
      setPublishing(false);
    }
  }

  const toPublish = receipt?.lines.filter((l) => l.status === "pending" && l.product && !l.is_weighted).length ?? 0;
  const toReview = receipt?.lines.filter((l) => l.status === "pending" && !l.product).length ?? 0;

  return (
    <View style={styles.screen}>
      <Header
        title="Ticket de caisse"
        subtitle={
          receipt
            ? [receipt.purchased_at && new Date(receipt.purchased_at).toLocaleDateString("fr-FR"),
               receipt.total != null && `total ${money(receipt.total)}`].filter(Boolean).join(" · ") || undefined
            : undefined
        }
        onBack={pop}
      />

      {reading ? (
        <Loading text="Lecture du ticket… quelques secondes." />
      ) : error && !receipt ? (
        <View style={{ padding: space.lg, gap: space.md }}>
          <ErrorBox message={error} />
          <Button label="Reprendre la photo" icon="camera" onPress={() => setCameraOpen(true)} />
        </View>
      ) : !receipt ? (
        <EmptyState
          icon="receipt-outline"
          title="Un ticket, des dizaines de prix"
          text="Photographie ton ticket de caisse : on lit chaque ligne, tu valides, et tous les prix sont partagés d'un coup. La photo reste privée."
          action={<Button label="Photographier le ticket" icon="camera" onPress={() => setCameraOpen(true)} />}
        />
      ) : done ? (
        <EmptyState
          icon="checkmark-circle-outline"
          title="Merci !"
          text={done}
          action={
            <View style={{ gap: space.sm }}>
              <Button label="Scanner un autre ticket" icon="camera" onPress={() => replace({ name: "receipt" })} />
              <Button label="Terminé" variant="secondary" onPress={pop} />
            </View>
          }
        />
      ) : (
        <>
          <ScrollView contentContainerStyle={styles.body}>
            {/* Magasin */}
            <Pressable onPress={() => setStorePicker(true)} style={[styles.store, !receipt.store && styles.storeMissing]}>
              <Ionicons name="storefront-outline" size={22} color={receipt.store ? colors.ink : colors.bad} />
              <View style={{ flex: 1 }}>
                <Text style={type.bodyStrong}>
                  {receipt.store ? receipt.store.chain : "Dans quel magasin ?"}
                </Text>
                <Text style={type.tiny} numberOfLines={1}>
                  {receipt.store
                    ? [receipt.store.name !== receipt.store.chain ? receipt.store.name : null, receipt.store.city].filter(Boolean).join(", ")
                    : receipt.detected_chain
                      ? `Enseigne lue sur le ticket : ${receipt.detected_chain}. Choisis le magasin exact.`
                      : "Choisis le magasin pour publier les prix."}
                </Text>
              </View>
              <Text style={styles.change}>{receipt.store ? "Changer" : "Choisir"}</Text>
            </Pressable>

            {receipt.warning && (
              <View style={styles.warning}>
                <Ionicons name="alert-circle-outline" size={18} color={colors.inkSoft} />
                <Text style={[type.small, { flex: 1, color: colors.inkSoft }]}>{receipt.warning}</Text>
              </View>
            )}

            <Text style={[type.small, { marginTop: space.lg, marginBottom: space.sm }]}>
              {receipt.counts.lines} ligne{receipt.counts.lines > 1 ? "s" : ""} lue{receipt.counts.lines > 1 ? "s" : ""}
              {toReview ? ` · ${toReview} à associer` : ""}. Vérifie les produits reconnus, associe les autres ou ignore-les.
            </Text>

            <View style={styles.lines}>
              {receipt.lines.map((line) => (
                <LineRow
                  key={line.id}
                  line={line}
                  onPick={() => setPicking(line)}
                  onIgnore={() => updateLine(line, { status: "ignored" })}
                  onRestore={() => updateLine(line, { status: "pending" })}
                />
              ))}
            </View>

            <Text style={[type.tiny, { marginTop: space.lg }]}>
              Seuls les prix sont partagés. La photo du ticket reste privée et sert uniquement de preuve.
            </Text>
          </ScrollView>

          <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
            <Button
              label={toPublish ? `Publier ${toPublish} prix` : "Rien à publier pour l'instant"}
              icon="checkmark"
              onPress={publish}
              loading={publishing}
              disabled={!toPublish || !receipt.store}
            />
            {!receipt.store && toPublish > 0 && (
              <Text style={[type.tiny, { textAlign: "center", color: colors.bad }]}>Choisis d'abord le magasin.</Text>
            )}
          </View>
        </>
      )}

      <ProofCamera mode="receipt" visible={cameraOpen} onClose={() => { setCameraOpen(false); if (!receipt) pop(); }} onCapture={read} />
      <ProductPicker
        visible={!!picking}
        label={picking?.label ?? ""}
        price={picking?.effective_unit_price ?? 0}
        onClose={() => setPicking(null)}
        onIgnore={() => {
          if (picking) updateLine(picking, { status: "ignored" });
          setPicking(null);
        }}
        onPick={(ean) => {
          if (picking) updateLine(picking, { ean });
          setPicking(null);
        }}
      />
      <StorePicker visible={storePicker} coords={coords} onClose={() => setStorePicker(false)} onPick={chooseStore} />
    </View>
  );
}

function LineRow({
  line,
  onPick,
  onIgnore,
  onRestore,
}: {
  line: ReceiptLine;
  onPick: () => void;
  onIgnore: () => void;
  onRestore: () => void;
}) {
  const muted = line.status === "ignored";
  return (
    <View style={[styles.line, muted && { opacity: 0.55 }]}>
      <Row style={{ alignItems: "flex-start" }}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={styles.receiptText} numberOfLines={2}>{line.label}</Text>
          <Text style={type.tiny}>
            {line.is_weighted
              ? `${line.quantity.toString().replace(".", ",")} kg × ${money(line.unit_price)}/kg`
              : line.quantity > 1
                ? `${line.quantity} × ${money(line.unit_price)}`
                : "1 article"}
            {line.discount ? ` · ${line.discount_label ?? "remise"} −${money(line.discount)}` : ""}
          </Text>
        </View>
        <PriceTag value={line.is_weighted ? line.line_total : line.effective_unit_price} size="sm" tone={muted ? "muted" : "ink"} />
      </Row>

      {line.status === "published" ? (
        <Row style={styles.matchRow}>
          <Ionicons name="checkmark-circle" size={18} color={colors.good} />
          <Text style={[type.small, { color: colors.good, flex: 1 }]} numberOfLines={1}>
            Publié : {line.product?.name}
          </Text>
        </Row>
      ) : line.is_weighted ? (
        <Text style={[type.tiny, styles.matchRow]}>Article au poids : bientôt pris en charge.</Text>
      ) : muted ? (
        <Row style={styles.matchRow}>
          <Text style={[type.tiny, { flex: 1 }]}>Ligne ignorée</Text>
          <Button label="Rétablir" variant="ghost" compact onPress={onRestore} />
        </Row>
      ) : line.product ? (
        <Pressable onPress={onPick} style={styles.matchRow}>
          <ProductThumb uri={line.product.image_url} size={32} />
          <View style={{ flex: 1 }}>
            <Text style={type.bodyStrong} numberOfLines={1}>{line.product.name}</Text>
            <Text style={[type.tiny, line.match_source === "fuzzy" && { color: colors.inkSoft }]}>
              {line.match_source === "mapping" ? "Reconnu grâce à la communauté" : line.match_source === "fuzzy" ? "Suggestion : vérifie" : "Associé par toi"}
            </Text>
          </View>
          <Text style={styles.change}>Changer</Text>
        </Pressable>
      ) : (
        <Row style={styles.matchRow}>
          <Button label="Associer un produit" icon="link-outline" compact onPress={onPick} style={{ flex: 1 }} />
          <IconButton icon="eye-off-outline" label="Ignorer cette ligne" onPress={onIgnore} size={40} />
        </Row>
      )}
    </View>
  );
}

function StorePicker({
  visible,
  coords,
  onClose,
  onPick,
}: {
  visible: boolean;
  coords: { latitude: number; longitude: number };
  onClose: () => void;
  onPick: (s: Store) => void;
}) {
  const insets = useSafeAreaInsets();
  const [stores, setStores] = useState<Store[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setStores(null);
    api.nearbyStores(coords, 5).then(setStores).catch((e) => setError(e.message));
  }, [visible, coords]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.screen, Platform.OS === "android" && { paddingTop: insets.top }]}>
        <View style={styles.pickerHead}>
          <Text style={[type.heading, { flex: 1 }]}>Magasin du ticket</Text>
          <IconButton icon="close" label="Fermer" onPress={onClose} />
        </View>
        <ScrollView contentContainerStyle={styles.body}>
          {error && <ErrorBox message={error} />}
          {!stores && !error && <Loading />}
          {stores?.length === 0 && <Text style={type.small}>Aucun magasin connu à moins de 5 km de ta position.</Text>}
          <View style={styles.lines}>
            {stores?.map((s) => (
              <Pressable key={s.id} onPress={() => onPick(s)} style={styles.storeRow}>
                <View style={{ flex: 1 }}>
                  <Text style={type.bodyStrong}>{s.chain}</Text>
                  <Text style={type.tiny} numberOfLines={1}>
                    {[s.name !== s.chain ? s.name : null, s.city].filter(Boolean).join(", ")}
                  </Text>
                </View>
                <Text style={type.small}>{distance(s.distance_km)}</Text>
              </Pressable>
            ))}
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: space.lg, paddingBottom: space.xxl },
  store: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  storeMissing: { borderWidth: 1, borderColor: colors.bad, backgroundColor: colors.badSoft },
  change: { fontFamily: fonts.semibold, fontSize: 14, color: colors.ink },
  warning: {
    flexDirection: "row",
    gap: space.sm,
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.navySoft,
  },
  lines: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden" },
  line: { padding: space.lg, gap: space.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line },
  // Le libellé est affiché tel qu'imprimé sur le ticket
  receiptText: { fontFamily: fonts.semibold, fontSize: 14, letterSpacing: 0.6, color: colors.inkSoft },
  matchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: space.sm,
  },
  footer: { padding: space.lg, paddingTop: space.md, gap: space.xs, borderTopWidth: 1, borderTopColor: colors.line },
  pickerHead: {
    flexDirection: "row",
    alignItems: "center",
    padding: space.lg,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    marginBottom: space.md,
  },
  storeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
});
