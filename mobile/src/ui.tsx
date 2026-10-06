import { Ionicons } from "@expo/vector-icons";
import React from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { imageUrl } from "./api";
import { priceParts } from "./format";
import { colors, fonts, radius, space, type } from "./theme";
import type { ConfidenceLevel } from "./types";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

/* ------------------------------------------------------------------ */
/* Étiquette de prix : l'élément signature de l'app.                    */
/* ------------------------------------------------------------------ */

const TAG_SIZES = {
  xl: { euros: 72, cents: 30, euro: 22, pad: 0 },
  lg: { euros: 44, cents: 20, euro: 16, pad: 0 },
  md: { euros: 28, cents: 14, euro: 12, pad: 0 },
  sm: { euros: 20, cents: 11, euro: 10, pad: 0 },
};

export function PriceTag({
  value,
  size = "md",
  tone = "ink",
  struck,
  style,
}: {
  value: number;
  size?: keyof typeof TAG_SIZES;
  tone?: "ink" | "white" | "promo" | "muted";
  struck?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const s = TAG_SIZES[size];
  const { euros, cents } = priceParts(value);
  const color =
    tone === "white" ? colors.white : tone === "promo" ? colors.promoInk : tone === "muted" ? colors.muted : colors.ink;
  return (
    <View style={[styles.tagRow, style]} accessible accessibilityLabel={`${euros} euros ${cents}`}>
      <Text style={[styles.tagEuros, { fontSize: s.euros, lineHeight: s.euros * 1.02, color }, struck && styles.struck]}>
        {euros}
      </Text>
      <View style={{ marginTop: s.euros * 0.1, marginLeft: 1 }}>
        <Text style={[styles.tagCents, { fontSize: s.cents, lineHeight: s.cents * 1.05, color }, struck && styles.struck]}>
          ,{cents}
        </Text>
        <Text style={[styles.tagEuro, { fontSize: s.euro, lineHeight: s.euro * 1.1, color }]}>€</Text>
      </View>
    </View>
  );
}

/** Sticker jaune des promos, légèrement de travers comme en rayon. */
export function PromoSticker({ label, small }: { label: string; small?: boolean }) {
  return (
    <View style={[styles.sticker, small && styles.stickerSmall]}>
      <Text style={[styles.stickerText, small && { fontSize: 12 }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

/* ------------------------------------------------------------------ */

export function Button({
  label,
  onPress,
  icon,
  variant = "primary",
  loading,
  disabled,
  style,
  compact,
}: {
  label: string;
  onPress?: () => void;
  icon?: IconName;
  variant?: "primary" | "secondary" | "ghost" | "danger" | "good";
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  compact?: boolean;
}) {
  const v = BUTTONS[variant];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.button,
        compact && styles.buttonCompact,
        { backgroundColor: v.bg, borderColor: v.border },
        (disabled || loading) && { opacity: 0.45 },
        pressed && { opacity: 0.8, transform: [{ scale: 0.99 }] },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={v.fg} />
      ) : (
        <>
          {icon && <Ionicons name={icon} size={compact ? 17 : 20} color={v.fg} />}
          <Text style={[styles.buttonText, compact && { fontSize: 15 }, { color: v.fg }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

const BUTTONS = {
  primary: { bg: colors.navy, fg: colors.white, border: colors.navy },
  secondary: { bg: colors.surface, fg: colors.ink, border: colors.line },
  ghost: { bg: "transparent", fg: colors.ink, border: "transparent" },
  danger: { bg: colors.badSoft, fg: colors.bad, border: colors.badSoft },
  good: { bg: colors.goodSoft, fg: colors.good, border: colors.goodSoft },
};

export function IconButton({
  icon,
  onPress,
  label,
  tone = "light",
  size = 42,
}: {
  icon: IconName;
  onPress: () => void;
  label: string;
  tone?: "light" | "dark" | "glass";
  size?: number;
}) {
  const bg = tone === "dark" ? colors.navy : tone === "glass" ? "rgba(10,18,36,0.55)" : colors.surface;
  const fg = tone === "light" ? colors.ink : colors.white;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={8}
      style={({ pressed }) => [
        styles.iconButton,
        { width: size, height: size, backgroundColor: bg, opacity: pressed ? 0.7 : 1 },
        tone === "light" && { borderWidth: 1, borderColor: colors.line },
      ]}
    >
      <Ionicons name={icon} size={size * 0.5} color={fg} />
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  sub,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  sub?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && { color: colors.white }]} numberOfLines={1}>
        {label}
      </Text>
      {sub ? <Text style={[styles.chipSub, selected && { color: "#C9D2E6" }]}>{sub}</Text> : null}
    </Pressable>
  );
}

/* ------------------------------------------------------------------ */

const CONFIDENCE = {
  high: { label: "Fiable", bars: 3, color: colors.good },
  medium: { label: "Plutôt fiable", bars: 2, color: colors.inkSoft },
  low: { label: "À vérifier", bars: 1, color: colors.bad },
};

export function Confidence({ level, showLabel = true }: { level: ConfidenceLevel; showLabel?: boolean }) {
  const c = CONFIDENCE[level];
  return (
    <View style={styles.confRow} accessibilityLabel={`Fiabilité : ${c.label}`}>
      <View style={styles.confBars}>
        {[0, 1, 2].map((i) => (
          <View
            key={i}
            style={[styles.confBar, { height: 6 + i * 3, backgroundColor: i < c.bars ? c.color : colors.line }]}
          />
        ))}
      </View>
      {showLabel && <Text style={[type.tiny, { color: c.color }]}>{c.label}</Text>}
    </View>
  );
}

const NUTRI = { a: "#038141", b: "#85BB2F", c: "#E5B300", d: "#EE8100", e: "#E63E11" } as Record<string, string>;

export function Nutriscore({ grade }: { grade?: string | null }) {
  if (!grade || !NUTRI[grade]) return null;
  return (
    <View style={[styles.nutri, { backgroundColor: NUTRI[grade] }]} accessibilityLabel={`Nutri-Score ${grade}`}>
      <Text style={styles.nutriText}>Nutri-Score {grade.toUpperCase()}</Text>
    </View>
  );
}

export function ProductThumb({ uri, size = 56 }: { uri?: string | null; size?: number }) {
  if (uri) {
    return <Image source={{ uri: imageUrl(uri) }} style={[styles.thumb, { width: size, height: size }]} resizeMode="contain" />;
  }
  return (
    <View style={[styles.thumb, styles.thumbEmpty, { width: size, height: size }]}>
      <Ionicons name="cube-outline" size={size * 0.42} color={colors.muted} />
    </View>
  );
}

export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: IconName;
  title: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIcon}>
        <Ionicons name={icon} size={28} color={colors.ink} />
      </View>
      <Text style={[type.heading, { textAlign: "center" }]}>{title}</Text>
      {text ? <Text style={[type.small, { textAlign: "center", maxWidth: 300 }]}>{text}</Text> : null}
      {action ? <View style={{ marginTop: space.sm, alignSelf: "stretch" }}>{action}</View> : null}
    </View>
  );
}

export function Loading({ text }: { text?: string }) {
  return (
    <View style={styles.loading}>
      <ActivityIndicator color={colors.ink} />
      {text ? <Text style={type.small}>{text}</Text> : null}
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.errorBox}>
      <Ionicons name="alert-circle" size={20} color={colors.bad} />
      <View style={{ flex: 1, gap: space.sm }}>
        <Text style={[type.small, { color: colors.bad }]}>{message}</Text>
        {onRetry && <Button label="Réessayer" onPress={onRetry} variant="secondary" compact style={{ alignSelf: "flex-start" }} />}
      </View>
    </View>
  );
}

export function Header({
  title,
  onBack,
  right,
  subtitle,
}: {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
  subtitle?: string;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.header, { paddingTop: insets.top + space.sm }]}>
      {onBack && <IconButton icon="chevron-back" label="Retour" onPress={onBack} />}
      <View style={{ flex: 1 }}>
        <Text style={type.title} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? <Text style={type.small}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export function SectionTitle({ children, right }: { children: string; right?: React.ReactNode }) {
  return (
    <View style={styles.sectionTitle}>
      <Text style={type.heading}>{children}</Text>
      {right}
    </View>
  );
}

export function Row({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: "row", alignItems: "center", gap: space.sm }, style]}>{children}</View>;
}

export function Meta({ icon, text, color, style }: { icon: IconName; text: string; color?: string; style?: StyleProp<TextStyle> }) {
  return (
    <View style={styles.meta}>
      <Ionicons name={icon} size={14} color={color ?? colors.muted} />
      <Text style={[type.tiny, color ? { color } : null, style]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tagRow: { flexDirection: "row", alignItems: "flex-start" },
  tagEuros: { fontFamily: fonts.displayHeavy, includeFontPadding: false },
  tagCents: { fontFamily: fonts.displayHeavy, includeFontPadding: false },
  tagEuro: { fontFamily: fonts.display, includeFontPadding: false },
  struck: { textDecorationLine: "line-through" },

  sticker: {
    backgroundColor: colors.promo,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 3,
    transform: [{ rotate: "-3deg" }],
    alignSelf: "flex-start",
  },
  stickerSmall: { paddingHorizontal: 7, paddingVertical: 2 },
  stickerText: { fontFamily: fonts.displayHeavy, fontSize: 15, color: colors.promoInk, letterSpacing: 0.2 },

  button: {
    minHeight: 54,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: space.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
  },
  buttonCompact: { minHeight: 40, paddingHorizontal: space.md },
  buttonText: { fontFamily: fonts.semibold, fontSize: 17 },

  iconButton: { borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },

  chip: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minWidth: 64,
  },
  chipSelected: { backgroundColor: colors.navy, borderColor: colors.navy },
  chipText: { fontFamily: fonts.semibold, fontSize: 15, color: colors.ink },
  chipSub: { fontFamily: fonts.medium, fontSize: 12, color: colors.muted, marginTop: 1 },

  confRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  confBars: { flexDirection: "row", alignItems: "flex-end", gap: 2 },
  confBar: { width: 4, borderRadius: 1 },

  nutri: { borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2, alignSelf: "flex-start" },
  nutriText: { fontFamily: fonts.bold, fontSize: 11, color: colors.white },

  thumb: { borderRadius: radius.sm, backgroundColor: colors.white },
  thumbEmpty: { backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center" },

  empty: { alignItems: "center", gap: space.sm, paddingVertical: space.xxl, paddingHorizontal: space.lg },
  emptyIcon: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.navySoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: space.xs,
  },
  loading: { alignItems: "center", gap: space.sm, paddingVertical: space.xxl },
  errorBox: {
    flexDirection: "row",
    gap: space.sm,
    backgroundColor: colors.badSoft,
    borderRadius: radius.md,
    padding: space.md,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    backgroundColor: colors.bg,
  },
  sectionTitle: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    marginTop: space.xl,
    marginBottom: space.sm,
  },
  meta: { flexDirection: "row", alignItems: "center", gap: 3 },
});
