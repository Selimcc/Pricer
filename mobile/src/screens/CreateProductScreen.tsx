import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { ProofCamera } from "../components/ProofCamera";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import { Button, ErrorBox, Header } from "../ui";

export function CreateProductScreen({ ean }: { ean: string }) {
  const { pop, replace, showToast, userId } = useApp();
  const insets = useSafeAreaInsets();
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [quantity, setQuantity] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.createProduct({
        ean,
        name: name.trim(),
        brand: brand.trim() || undefined,
        quantity: quantity.trim() || undefined,
        user_id: userId,
      });
      if (photo) {
        try {
          await api.uploadProductImage(ean, userId, photo);
        } catch {
          showToast("Produit ajouté, mais la photo n'a pas pu être envoyée.", "info");
          replace({ name: "product", ean });
          return;
        }
      }
      showToast("Produit ajouté au catalogue. Merci !", "success");
      replace({ name: "product", ean });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Le produit n'a pas pu être ajouté.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Header title="Nouveau produit" subtitle={`Code-barres ${ean}`} onBack={pop} />
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={type.small}>
          Aucune base ne connaît encore ce produit. Recopie ce qui est écrit sur l'emballage : il sera disponible pour
          tout le monde, quel que soit le rayon (alimentation, hygiène, entretien…).
        </Text>

        <Pressable
          onPress={() => setCameraOpen(true)}
          style={styles.photoBox}
          accessibilityRole="button"
          accessibilityLabel={photo ? "Reprendre la photo du produit" : "Photographier le produit"}
        >
          {photo ? (
            <Image source={{ uri: photo }} style={styles.photo} resizeMode="cover" />
          ) : (
            <View style={styles.photoEmpty}>
              <Ionicons name="camera-outline" size={28} color={colors.ink} />
              <Text style={type.bodyStrong}>Photo de l'emballage</Text>
              <Text style={type.tiny}>Recommandé : aide les autres à reconnaître le produit</Text>
            </View>
          )}
        </Pressable>

        <Field label="Nom du produit" value={name} onChange={setName} placeholder="Ex. Lessive liquide fraîcheur" />
        <Field label="Marque" value={brand} onChange={setBrand} placeholder="Ex. Skip" />
        <Field
          label="Quantité"
          value={quantity}
          onChange={setQuantity}
          placeholder="Ex. 1,5 L, 500 g, 6 x 33 cl"
          help="Sert à calculer le prix au kilo ou au litre."
        />
        {error && <ErrorBox message={error} />}
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
        <Button label="Ajouter le produit" icon="checkmark" onPress={save} loading={saving} disabled={name.trim().length < 2} />
      </View>
      <ProofCamera
        mode="product"
        visible={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCapture={(uri) => {
          setPhoto(uri);
          setCameraOpen(false);
        }}
      />
    </KeyboardAvoidingView>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  help?: string;
}) {
  return (
    <View style={{ gap: space.xs }}>
      <Text style={type.bodyStrong}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={styles.input}
        accessibilityLabel={label}
      />
      {help ? <Text style={type.tiny}>{help}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { padding: space.lg, gap: space.lg },
  photoBox: { borderRadius: radius.lg, overflow: "hidden" },
  photo: { width: "100%", height: 200 },
  photoEmpty: {
    height: 140,
    borderRadius: radius.lg,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: colors.line,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    fontFamily: fonts.medium,
    fontSize: 17,
    color: colors.ink,
  },
  footer: { padding: space.lg, borderTopWidth: 1, borderTopColor: colors.line },
});
