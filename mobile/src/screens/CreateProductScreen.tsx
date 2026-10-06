import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { useApp } from "../state";
import { colors, fonts, radius, space, type } from "../theme";
import { Button, ErrorBox, Header } from "../ui";

export function CreateProductScreen({ ean }: { ean: string }) {
  const { pop, replace, showToast } = useApp();
  const insets = useSafeAreaInsets();
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [quantity, setQuantity] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.createProduct({ ean, name: name.trim(), brand: brand.trim() || undefined, quantity: quantity.trim() || undefined });
      showToast("Produit ajouté. Merci !", "success");
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
          Recopie ce qui est écrit sur l'emballage. Le produit sera disponible pour tous dès maintenant.
        </Text>
        <Field label="Nom du produit" value={name} onChange={setName} placeholder="Ex. Lait demi-écrémé" autoFocus />
        <Field label="Marque" value={brand} onChange={setBrand} placeholder="Ex. Lactel" />
        <Field
          label="Quantité"
          value={quantity}
          onChange={setQuantity}
          placeholder="Ex. 1 L, 500 g, 6 x 33 cl"
          help="Sert à calculer le prix au kilo ou au litre."
        />
        {error && <ErrorBox message={error} />}
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
        <Button label="Ajouter le produit" icon="checkmark" onPress={save} loading={saving} disabled={name.trim().length < 2} />
      </View>
    </KeyboardAvoidingView>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  help?: string;
  autoFocus?: boolean;
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
        autoFocus={autoFocus}
        accessibilityLabel={label}
      />
      {help ? <Text style={type.tiny}>{help}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { padding: space.lg, gap: space.lg },
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
