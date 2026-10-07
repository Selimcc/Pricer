import React, { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { api } from "../api";
import { API_URL, FORCE_DEMO_LOCATION } from "../config";
import { relativeDate } from "../format";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import type { Contributions, ReceiptSummary } from "../types";
import { Button, EmptyState, ErrorBox, Header, Loading, PriceTag, ProductThumb, Row, SectionTitle } from "../ui";

export function ProfileScreen() {
  const { userId, push, useDemoLocation, setUseDemoLocation, locationMode } = useApp();
  const [data, setData] = useState<Contributions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [receipts, setReceipts] = useState<ReceiptSummary[]>([]);

  const load = useCallback(async () => {
    if (!userId) return;
    setError(null);
    try {
      setData(await api.contributions(userId));
      api.receipts(userId).then(setReceipts).catch(() => setReceipts([]));
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

        {receipts.length > 0 && (
          <>
            <SectionTitle>Tes tickets</SectionTitle>
            <View style={styles.list}>
              {receipts.slice(0, 10).map((r) => (
                <Pressable key={r.id} style={styles.row} onPress={() => push({ name: "receipt", id: r.id })}>
                  <View style={{ flex: 1 }}>
                    <Text style={type.bodyStrong} numberOfLines={1}>{r.chain ?? "Magasin à préciser"}</Text>
                    <Text style={type.tiny}>
                      {relativeDate(r.purchased_at ?? r.created_at)} · {r.lines} ligne{r.lines > 1 ? "s" : ""}
                    </Text>
                  </View>
                  <Text style={[type.tiny, { color: r.status === "published" ? colors.good : colors.bad }]}>
                    {r.status === "published" ? "Publié" : "À finir"}
                  </Text>
                </Pressable>
              ))}
            </View>
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
          <ServerSetting />
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

/** Adresse du serveur : Wi-Fi à la maison, tunnel https en magasin. Modifiable sans relancer l'app. */
function ServerSetting() {
  const { serverUrl, setServerUrl, showToast } = useApp();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(serverUrl);
  const [testing, setTesting] = useState(false);

  async function save() {
    const url = value.trim().replace(/\/$/, "");
    if (!/^https?:\/\/.+/.test(url)) {
      showToast("L'adresse doit commencer par http:// ou https://", "error");
      return;
    }
    const previous = serverUrl;
    setServerUrl(url);
    setTesting(true);
    try {
      const h = await api.health();
      showToast(`Serveur joignable (API ${h.version}).`, "success");
      setEditing(false);
    } catch (e) {
      setServerUrl(previous === API_URL ? null : previous);
      showToast(e instanceof Error ? e.message : "Serveur injoignable.", "error");
    } finally {
      setTesting(false);
    }
  }

  return (
    <View style={styles.setting}>
      <Row style={{ justifyContent: "space-between" }}>
        <Text style={type.bodyStrong}>Serveur</Text>
        {!editing && (
          <Pressable onPress={() => { setValue(serverUrl); setEditing(true); }} hitSlop={8}>
            <Text style={[type.small, { color: colors.ink, fontFamily: fonts.semibold }]}>Modifier</Text>
          </Pressable>
        )}
      </Row>
      {editing ? (
        <View style={{ gap: space.sm, marginTop: space.xs }}>
          <TextInput
            value={value}
            onChangeText={setValue}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="https://xxx.trycloudflare.com"
            placeholderTextColor={colors.muted}
            style={styles.serverInput}
          />
          <Text style={type.tiny}>
            À la maison : l'adresse Wi-Fi du PC. En magasin : l'adresse du tunnel affichée par « docker compose logs tunnel ».
          </Text>
          <Row>
            <Button label="Tester et enregistrer" compact onPress={save} loading={testing} style={{ flex: 1 }} />
            <Button label="Annuler" variant="ghost" compact onPress={() => setEditing(false)} />
          </Row>
          {serverUrl !== API_URL && (
            <Button
              label="Revenir à l'adresse du .env"
              variant="ghost"
              compact
              onPress={() => { setServerUrl(null); setEditing(false); }}
            />
          )}
        </View>
      ) : (
        <Text style={type.tiny}>{serverUrl}</Text>
      )}
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
  serverInput: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    fontFamily: fonts.medium,
    fontSize: 15,
    color: colors.ink,
  },
  setting: { padding: space.lg, gap: 2, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line },
});
