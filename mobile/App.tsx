import { Barlow_400Regular } from "@expo-google-fonts/barlow/400Regular";
import { Barlow_500Medium } from "@expo-google-fonts/barlow/500Medium";
import { Barlow_600SemiBold } from "@expo-google-fonts/barlow/600SemiBold";
import { Barlow_700Bold } from "@expo-google-fonts/barlow/700Bold";
import { BarlowCondensed_700Bold } from "@expo-google-fonts/barlow-condensed/700Bold";
import { BarlowCondensed_800ExtraBold } from "@expo-google-fonts/barlow-condensed/800ExtraBold";
import { Ionicons } from "@expo/vector-icons";
import { useFonts } from "expo-font";
import { StatusBar } from "expo-status-bar";
import React, { useEffect } from "react";
import { ActivityIndicator, BackHandler, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";

import { CreateProductScreen } from "./src/screens/CreateProductScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { ListScreen } from "./src/screens/ListScreen";
import { ProductScreen } from "./src/screens/ProductScreen";
import { ProfileScreen } from "./src/screens/ProfileScreen";
import { ScannerScreen } from "./src/screens/ScannerScreen";
import { StoreScreen } from "./src/screens/StoreScreen";
import { StoresScreen } from "./src/screens/StoresScreen";
import { AppProvider, type Route, type Tab, useApp } from "./src/state";
import { colors, fonts, space } from "./src/theme";

export default function App() {
  const [fontsLoaded, fontError] = useFonts({
    Barlow_400Regular,
    Barlow_500Medium,
    Barlow_600SemiBold,
    Barlow_700Bold,
    BarlowCondensed_700Bold,
    BarlowCondensed_800ExtraBold,
  });

  // En cas d'échec de chargement des polices, on continue avec celles du système.
  if (!fontsLoaded && !fontError) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.ink} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <AppProvider>
        <StatusBar style="dark" />
        <Root />
      </AppProvider>
    </SafeAreaProvider>
  );
}

function Root() {
  const { ready, tab, stack, pop } = useApp();

  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (stack.length > 0) {
        pop();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [stack.length, pop]);

  if (!ready) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.ink} />
      </View>
    );
  }

  const top = stack[stack.length - 1];
  return (
    <View style={styles.root}>
      {top ? (
        <RouteView route={top} key={stack.length + JSON.stringify(top)} />
      ) : (
        <>
          <View style={{ flex: 1 }}>
            <TabView tab={tab} />
          </View>
          <TabBar />
        </>
      )}
      <ToastView />
    </View>
  );
}

function TabView({ tab }: { tab: Tab }) {
  switch (tab) {
    case "home":
      return <HomeScreen />;
    case "list":
      return <ListScreen />;
    case "stores":
      return <StoresScreen />;
    case "me":
      return <ProfileScreen />;
  }
}

function RouteView({ route }: { route: Route }) {
  switch (route.name) {
    case "scanner":
      return <ScannerScreen mode={route.mode} />;
    case "product":
      return <ProductScreen ean={route.ean} />;
    case "store":
      return <StoreScreen id={route.id} />;
    case "createProduct":
      return <CreateProductScreen ean={route.ean} />;
  }
}

type IconName = keyof typeof Ionicons.glyphMap;

const TABS: { key: Tab; label: string; icon: IconName; active: IconName }[] = [
  { key: "home", label: "Accueil", icon: "home-outline", active: "home" },
  { key: "list", label: "Ma liste", icon: "cart-outline", active: "cart" },
  { key: "stores", label: "Magasins", icon: "storefront-outline", active: "storefront" },
  { key: "me", label: "Moi", icon: "person-outline", active: "person" },
];

function TabBar() {
  const { tab, setTab, push } = useApp();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.tabBar, { paddingBottom: Math.max(insets.bottom, space.sm) }]}>
      {TABS.slice(0, 2).map((t) => (
        <TabButton key={t.key} t={t} selected={tab === t.key} onPress={() => setTab(t.key)} />
      ))}
      <Pressable
        onPress={() => push({ name: "scanner", mode: "lookup" })}
        style={({ pressed }) => [styles.scanTab, pressed && { transform: [{ scale: 0.96 }] }]}
        accessibilityRole="button"
        accessibilityLabel="Scanner un produit"
      >
        <Ionicons name="scan" size={28} color={colors.ink} />
      </Pressable>
      {TABS.slice(2).map((t) => (
        <TabButton key={t.key} t={t} selected={tab === t.key} onPress={() => setTab(t.key)} />
      ))}
    </View>
  );
}

function TabButton({ t, selected, onPress }: { t: (typeof TABS)[number]; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={styles.tab}
      accessibilityRole="tab"
      accessibilityState={{ selected }}
      accessibilityLabel={t.label}
    >
      <Ionicons name={selected ? t.active : t.icon} size={23} color={selected ? colors.ink : colors.muted} />
      <Text style={[styles.tabText, selected && { color: colors.ink, fontFamily: fonts.semibold }]}>{t.label}</Text>
    </Pressable>
  );
}

function ToastView() {
  const { toast } = useApp();
  const insets = useSafeAreaInsets();
  if (!toast) return null;
  const bg = toast.kind === "error" ? colors.bad : toast.kind === "success" ? colors.good : colors.navy;
  return (
    <View pointerEvents="none" style={[styles.toastWrap, { top: insets.top + space.sm }]}>
      <View style={[styles.toast, { backgroundColor: bg }]} accessibilityLiveRegion="polite">
        <Ionicons
          name={toast.kind === "error" ? "alert-circle" : toast.kind === "success" ? "checkmark-circle" : "information-circle"}
          size={20}
          color={colors.white}
        />
        <Text style={styles.toastText}>{toast.message}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { alignItems: "center", justifyContent: "center" },
  tabBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    paddingTop: space.sm,
  },
  tab: { flex: 1, alignItems: "center", gap: 2, paddingVertical: 2 },
  tabText: { fontFamily: fonts.medium, fontSize: 11, color: colors.muted },
  scanTab: {
    width: 58,
    height: 58,
    borderRadius: 18,
    backgroundColor: colors.promo,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -22,
    marginHorizontal: space.xs,
    borderWidth: 4,
    borderColor: colors.bg,
  },
  toastWrap: { position: "absolute", left: space.lg, right: space.lg, alignItems: "center" },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    borderRadius: 12,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    maxWidth: 520,
  },
  toastText: { flex: 1, fontFamily: fonts.semibold, fontSize: 15, color: colors.white },
});
