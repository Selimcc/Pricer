import { Ionicons } from "@expo/vector-icons";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import * as Haptics from "expo-haptics";
import React, { useEffect, useRef, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { isValidBarcode, money } from "../format";
import { colors, fonts, radius, space, type } from "../theme";
import type { Product } from "../types";
import { Button, IconButton, ProductThumb } from "../ui";

/**
 * Associer une ligne de ticket à un produit : scanner l'article (le plus
 * fiable, on a souvent le produit sous la main) ou le chercher par son nom.
 */
export function ProductPicker({
  visible,
  label,
  price,
  onPick,
  onIgnore,
  onClose,
}: {
  visible: boolean;
  label: string;
  price: number;
  onPick: (ean: string) => void;
  onIgnore: () => void;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const locked = useRef(false);

  useEffect(() => {
    if (visible) {
      // Le libellé du ticket est souvent une bonne première recherche
      const words = label.split(" ").filter((w) => /[A-Z]{3,}/.test(w)).slice(0, 2).join(" ");
      setQuery(words);
      setScanning(false);
      locked.current = false;
      search(words);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, label]);

  function search(text: string) {
    if (timer.current) clearTimeout(timer.current);
    if (text.trim().length < 2) {
      setResults([]);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        setResults(await api.searchProducts(text.trim()));
      } catch {
        setResults([]);
      }
    }, 250);
  }

  function onScan({ data }: BarcodeScanningResult) {
    const code = data.replace(/\D/g, "");
    if (locked.current || !isValidBarcode(code)) return;
    locked.current = true;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    onPick(code);
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.sheet, Platform.OS === "android" && { paddingTop: insets.top }]}>
        <View style={styles.head}>
          <View style={{ flex: 1 }}>
            <Text style={type.heading}>Quel produit ?</Text>
            <Text style={styles.receiptLabel} numberOfLines={1}>
              {label} · {money(price)}
            </Text>
          </View>
          <IconButton icon="close" label="Fermer" onPress={onClose} />
        </View>

        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {scanning && permission?.granted ? (
            <View style={styles.cameraBox}>
              <CameraView
                style={StyleSheet.absoluteFill}
                facing="back"
                onBarcodeScanned={onScan}
                barcodeScannerSettings={{ barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"] }}
              />
              <View style={styles.cameraHint}>
                <Text style={styles.cameraHintText}>Vise le code-barres de l'article</Text>
              </View>
            </View>
          ) : (
            <Button
              label="Scanner l'article"
              icon="barcode-outline"
              onPress={async () => {
                if (!permission?.granted) {
                  const r = await requestPermission();
                  if (!r.granted) return;
                }
                setScanning(true);
              }}
            />
          )}

          <Text style={[type.bodyStrong, { marginTop: space.xl }]}>Ou cherche-le</Text>
          <View style={styles.search}>
            <Ionicons name="search" size={18} color={colors.muted} />
            <TextInput
              value={query}
              onChangeText={(t) => {
                setQuery(t);
                search(t);
              }}
              placeholder="Nom ou marque"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              autoCapitalize="none"
            />
          </View>
          {results.length > 0 ? (
            <View style={styles.results}>
              {results.slice(0, 8).map((p) => (
                <Pressable key={p.ean} onPress={() => onPick(p.ean)} style={styles.result}>
                  <ProductThumb uri={p.image_url} size={40} />
                  <View style={{ flex: 1 }}>
                    <Text style={type.bodyStrong} numberOfLines={1}>{p.name}</Text>
                    <Text style={type.tiny} numberOfLines={1}>{[p.brand, p.quantity].filter(Boolean).join(" · ")}</Text>
                  </View>
                  <Ionicons name="checkmark-circle-outline" size={24} color={colors.navy} />
                </Pressable>
              ))}
            </View>
          ) : query.trim().length >= 2 ? (
            <Text style={[type.small, { marginTop: space.sm }]}>
              Pas trouvé dans le catalogue : scanne l'article, il sera ajouté automatiquement.
            </Text>
          ) : null}

          <Button
            label="Ignorer cette ligne"
            variant="ghost"
            icon="eye-off-outline"
            onPress={onIgnore}
            style={{ marginTop: space.xl }}
          />
        </ScrollView>
      </View>
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
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  receiptLabel: { fontFamily: fonts.semibold, fontSize: 14, color: colors.inkSoft, letterSpacing: 0.3 },
  body: { padding: space.lg, paddingBottom: space.xxl },
  cameraBox: { height: 220, borderRadius: radius.lg, overflow: "hidden", backgroundColor: "#000" },
  cameraHint: { position: "absolute", bottom: space.md, left: 0, right: 0, alignItems: "center" },
  cameraHintText: { ...type.bodyStrong, color: colors.white, textShadowColor: "#000", textShadowRadius: 6 },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: space.md,
    marginTop: space.sm,
  },
  searchInput: { flex: 1, paddingVertical: 13, fontFamily: fonts.medium, fontSize: 16, color: colors.ink },
  results: { backgroundColor: colors.surface, borderRadius: radius.md, marginTop: space.sm, overflow: "hidden" },
  result: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
});
