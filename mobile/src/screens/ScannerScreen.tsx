import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import * as Haptics from "expo-haptics";
import React, { useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError, api } from "../api";
import { isValidBarcode } from "../format";
import { useApp } from "../state";
import { colors, fonts, space, type } from "../theme";
import { Button, EmptyState, IconButton } from "../ui";

export function ScannerScreen({ mode }: { mode: "lookup" | "list" }) {
  const { replace, pop, userId, showToast, bumpList } = useApp();
  const [permission, requestPermission] = useCameraPermissions();
  const [torch, setTorch] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [added, setAdded] = useState(0);
  const busy = useRef(false);
  const lastCode = useRef<{ code: string; at: number } | null>(null);
  const insets = useSafeAreaInsets();

  async function onScan({ data }: BarcodeScanningResult) {
    if (busy.current) return;
    const code = data.replace(/\D/g, "");
    if (!isValidBarcode(code)) {
      setHint("Lecture imparfaite : garde le code-barres bien à plat et éclairé.");
      return;
    }
    const now = Date.now();
    if (lastCode.current && lastCode.current.code === code && now - lastCode.current.at < 2500) return;
    lastCode.current = { code, at: now };
    busy.current = true;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});

    if (mode === "lookup") {
      replace({ name: "product", ean: code });
      return;
    }
    try {
      const item = await api.addToList(userId, code);
      bumpList();
      setAdded((n) => n + 1);
      setHint(null);
      showToast(`Ajouté : ${item.product.name}`, "success");
    } catch (e) {
      if (e instanceof ApiError && e.code === "product_not_found") {
        showToast("Produit inconnu : ajoute-le d'abord.", "error");
        replace({ name: "createProduct", ean: code });
        return;
      }
      showToast(e instanceof Error ? e.message : "Impossible d'ajouter ce produit.", "error");
    } finally {
      setTimeout(() => (busy.current = false), 900);
    }
  }

  if (!permission) return <View style={styles.dark} />;

  if (!permission.granted) {
    return (
      <View style={[styles.permission, { paddingTop: insets.top + space.lg }]}>
        <View style={{ alignSelf: "flex-start" }}>
          <IconButton icon="close" label="Fermer" onPress={pop} />
        </View>
        <EmptyState
          icon="camera-outline"
          title="La caméra sert à lire les codes-barres"
          text="Aucune photo n'est prise pendant le scan. Tu peux aussi taper le code à la main depuis l'accueil."
          action={<Button label="Autoriser la caméra" icon="camera" onPress={requestPermission} />}
        />
      </View>
    );
  }

  return (
    <View style={styles.dark}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        onBarcodeScanned={onScan}
        barcodeScannerSettings={{ barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"] }}
      />
      <View style={[styles.top, { paddingTop: insets.top + space.sm }]}>
        <IconButton icon="close" label="Fermer le scanner" tone="glass" onPress={pop} />
        <Text style={styles.title}>{mode === "list" ? "Ajouter à ma liste" : "Scanner un produit"}</Text>
        <IconButton
          icon={torch ? "flash" : "flash-outline"}
          label={torch ? "Éteindre la lampe" : "Allumer la lampe"}
          tone="glass"
          onPress={() => setTorch((t) => !t)}
        />
      </View>

      <View style={styles.frameWrap} pointerEvents="none">
        <View style={styles.frame}>
          <View style={[styles.corner, styles.tl]} />
          <View style={[styles.corner, styles.tr]} />
          <View style={[styles.corner, styles.bl]} />
          <View style={[styles.corner, styles.br]} />
          <View style={styles.laser} />
        </View>
      </View>

      <View style={[styles.bottom, { paddingBottom: insets.bottom + space.lg }]}>
        <Text style={styles.hint}>
          {hint ??
            (mode === "list"
              ? added > 0
                ? `${added} produit${added > 1 ? "s" : ""} ajouté${added > 1 ? "s" : ""}. Continue ou termine.`
                : "Scanne les produits un par un, ils s'ajoutent à ta liste."
              : "Vise le code-barres, la recherche part toute seule.")}
        </Text>
        {mode === "list" ? (
          <Button label="Terminé" icon="checkmark" onPress={pop} />
        ) : (
          <Button label="Taper le code à la main" variant="secondary" icon="keypad-outline" onPress={pop} />
        )}
      </View>
    </View>
  );
}

const C = 28;
const styles = StyleSheet.create({
  dark: { flex: 1, backgroundColor: "#000" },
  permission: { flex: 1, backgroundColor: colors.bg, padding: space.lg },
  top: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: space.lg,
  },
  title: { fontFamily: fonts.display, fontSize: 22, color: colors.white },
  frameWrap: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, alignItems: "center", justifyContent: "center" },
  frame: { width: "80%", height: 170 },
  corner: { position: "absolute", width: C, height: C, borderColor: colors.promo },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 6 },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 6 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 6 },
  br: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 6 },
  laser: { position: "absolute", left: 16, right: 16, top: "50%", height: 2, backgroundColor: "rgba(255,210,63,0.7)" },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, padding: space.lg, gap: space.md },
  hint: { ...type.bodyStrong, color: colors.white, textAlign: "center", textShadowColor: "#000", textShadowRadius: 6 },
});
