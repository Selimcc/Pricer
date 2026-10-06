/**
 * Langage visuel : le rayon de supermarché.
 * - bleu marine pour l'interface (texte, actions principales) ;
 * - jaune « sticker promo » réservé aux promotions ;
 * - vert uniquement pour l'argent économisé et ce qui est vérifié ;
 * - les prix s'écrivent comme sur une étiquette (Barlow Condensed, centimes surélevés).
 */
export const colors = {
  bg: "#ECEFF4",
  surface: "#FFFFFF",
  surfaceAlt: "#F5F7FA",
  ink: "#14213D",
  inkSoft: "#3B4866",
  muted: "#6C7690",
  line: "#DADFE8",
  navy: "#14213D",
  navySoft: "#E2E7F1",
  promo: "#FFD23F",
  promoInk: "#3A2C00",
  good: "#0B7A52",
  goodSoft: "#DFF2E9",
  bad: "#C2362C",
  badSoft: "#FBE7E5",
  white: "#FFFFFF",
};

export const fonts = {
  body: "Barlow_400Regular",
  medium: "Barlow_500Medium",
  semibold: "Barlow_600SemiBold",
  bold: "Barlow_700Bold",
  display: "BarlowCondensed_700Bold",
  displayHeavy: "BarlowCondensed_800ExtraBold",
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

export const radius = { sm: 6, md: 10, lg: 16, pill: 999 };

export const type = {
  title: { fontFamily: fonts.display, fontSize: 30, lineHeight: 32, color: colors.ink },
  heading: { fontFamily: fonts.display, fontSize: 22, lineHeight: 26, color: colors.ink },
  body: { fontFamily: fonts.body, fontSize: 16, lineHeight: 22, color: colors.ink },
  bodyStrong: { fontFamily: fonts.semibold, fontSize: 16, lineHeight: 22, color: colors.ink },
  small: { fontFamily: fonts.medium, fontSize: 14, lineHeight: 19, color: colors.muted },
  tiny: { fontFamily: fonts.medium, fontSize: 12, lineHeight: 16, color: colors.muted },
} as const;
