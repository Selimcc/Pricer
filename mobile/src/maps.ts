import { Linking, Platform } from "react-native";

/** Ouvre l'itinéraire vers un magasin dans l'app de cartes du téléphone. */
export function openDirections(latitude: number, longitude: number, label: string) {
  const q = encodeURIComponent(label);
  const url =
    Platform.OS === "ios"
      ? `http://maps.apple.com/?daddr=${latitude},${longitude}&q=${q}`
      : `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`;
  Linking.openURL(url).catch(() => {});
}
