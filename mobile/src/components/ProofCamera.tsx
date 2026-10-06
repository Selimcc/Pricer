import { CameraView, useCameraPermissions } from "expo-camera";
import React, { useRef, useState } from "react";
import { Modal, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fonts, space, type } from "../theme";
import { Button, EmptyState, IconButton } from "../ui";

/** Appareil photo plein écran pour photographier l'étiquette ou le ticket. */
export function ProofCamera({
  visible,
  onClose,
  onCapture,
}: {
  visible: boolean;
  onClose: () => void;
  onCapture: (uri: string) => void;
}) {
  const [permission, requestPermission] = useCameraPermissions();
  const [taking, setTaking] = useState(false);
  const camera = useRef<CameraView>(null);
  const insets = useSafeAreaInsets();

  async function take() {
    if (!camera.current || taking) return;
    setTaking(true);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.5, skipProcessing: false });
      if (photo?.uri) onCapture(photo.uri);
    } finally {
      setTaking(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} presentationStyle="fullScreen">
      {!permission?.granted ? (
        <View style={[styles.permission, { paddingTop: insets.top + space.lg }]}>
          <View style={{ alignSelf: "flex-start" }}>
            <IconButton icon="close" label="Fermer" onPress={onClose} />
          </View>
          <EmptyState
            icon="camera-outline"
            title="Photographier l'étiquette"
            text="La photo prouve le prix affiché. Elle est rattachée à ton relevé et visible par la communauté."
            action={<Button label="Autoriser la caméra" icon="camera" onPress={requestPermission} />}
          />
        </View>
      ) : (
        <View style={styles.dark}>
          <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" />
          <View style={[styles.top, { paddingTop: insets.top + space.sm }]}>
            <IconButton icon="close" label="Annuler" tone="glass" onPress={onClose} />
            <Text style={styles.title}>Étiquette de prix</Text>
            <View style={{ width: 42 }} />
          </View>
          <View style={[styles.bottom, { paddingBottom: insets.bottom + space.lg }]}>
            <Text style={styles.hint}>Cadre l'étiquette entière : prix, nom du produit, prix au kilo.</Text>
            <Button label="Prendre la photo" icon="camera" onPress={take} loading={taking} />
          </View>
        </View>
      )}
    </Modal>
  );
}

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
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, padding: space.lg, gap: space.md },
  hint: { ...type.bodyStrong, color: colors.white, textAlign: "center", textShadowColor: "#000", textShadowRadius: 6 },
});
