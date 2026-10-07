import React, { useEffect, useMemo, useState } from "react";
import { GestureResponderEvent, LayoutChangeEvent, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Line, Text as SvgText } from "react-native-svg";

import { money } from "../format";
import { colors, fonts, space, type } from "../theme";

/** Couleurs validées (lisibles en daltonisme) : bleu = prix normal, ambre = promotion. */
const NORMAL = "#2F5DA8";
const PROMO = "#C98F00";
const GRID = colors.line;
const SURFACE = colors.surface;

export type HistoryPoint = {
  observed_at: string;
  price: number;
  is_promotion: boolean;
  chain: string;
  store_name: string;
};

const HEIGHT = 150;
const PAD = { top: 12, right: 12, bottom: 22, left: 40 };

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }).replace(".", "");

/**
 * Nuage de points des relevés dans le temps, avec la médiane en repère.
 * Toucher le graphique sélectionne le relevé le plus proche (date) et l'affiche dessous.
 */
export function PriceHistoryChart({ points, median }: { points: HistoryPoint[]; median?: number | null }) {
  const [width, setWidth] = useState(0);
  const [selected, setSelected] = useState(points.length - 1);
  useEffect(() => setSelected(points.length - 1), [points.length]);

  const scale = useMemo(() => {
    const times = points.map((p) => new Date(p.observed_at).getTime());
    const prices = points.map((p) => p.price);
    const t0 = Math.min(...times);
    const t1 = Math.max(...times);
    // Graduations rondes (0,10 / 0,20 / 0,50 / 1 €…) encadrant les prix
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const raw = Math.max((max - min) / 3, 0.05);
    const step = [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20].find((c) => c >= raw) ?? 50;
    let lo = Math.floor(min / step) * step;
    let hi = Math.ceil(max / step) * step;
    if (hi - lo < step) hi = lo + step;
    if (min - lo < step * 0.15) lo -= step;
    if (hi - max < step * 0.15) hi += step;
    const ticks: number[] = [];
    for (let t = lo; t <= hi + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
    const innerW = Math.max(1, width - PAD.left - PAD.right);
    const innerH = HEIGHT - PAD.top - PAD.bottom;
    const x = (t: number) => PAD.left + (t1 === t0 ? innerW / 2 : ((t - t0) / (t1 - t0)) * innerW);
    const y = (p: number) => PAD.top + (hi === lo ? innerH / 2 : (1 - (p - lo) / (hi - lo)) * innerH);
    return { times, lo, hi, x, y, ticks };
  }, [points, width]);

  function pick(e: GestureResponderEvent) {
    const px = e.nativeEvent.locationX;
    let best = 0;
    let bestD = Infinity;
    scale.times.forEach((t, i) => {
      const d = Math.abs(scale.x(t) - px);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    setSelected(best);
  }

  const sel = points[Math.min(selected, points.length - 1)];
  const ticks = scale.ticks;
  const hasPromo = points.some((p) => p.is_promotion);

  return (
    <View>
      <View
        onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={pick}
        onResponderMove={pick}
        accessible
        accessibilityLabel={`Évolution du prix : ${points.length} relevés entre ${money(Math.min(...points.map((p) => p.price)))} et ${money(Math.max(...points.map((p) => p.price)))}`}
      >
        {width > 0 && (
          <Svg width={width} height={HEIGHT}>
            {ticks.map((t) => (
              <React.Fragment key={t}>
                <Line x1={PAD.left} x2={width - PAD.right} y1={scale.y(t)} y2={scale.y(t)} stroke={GRID} strokeWidth={1} />
                <SvgText x={PAD.left - 6} y={scale.y(t) + 4} fontSize={11} fill={colors.muted} textAnchor="end" fontFamily={fonts.medium}>
                  {t.toFixed(2).replace(".", ",")}
                </SvgText>
              </React.Fragment>
            ))}

            {median != null && (
              <Line x1={PAD.left} x2={width - PAD.right} y1={scale.y(median)} y2={scale.y(median)} stroke={colors.inkSoft} strokeWidth={1.5} opacity={0.7} />
            )}

            {/* Repère vertical sur le relevé sélectionné */}
            {sel && (
              <Line
                x1={scale.x(scale.times[selected])}
                x2={scale.x(scale.times[selected])}
                y1={PAD.top}
                y2={HEIGHT - PAD.bottom}
                stroke={colors.ink}
                strokeWidth={1}
                opacity={0.25}
              />
            )}

            {points.map((p, i) => (
              <Circle
                key={i}
                cx={scale.x(scale.times[i])}
                cy={scale.y(p.price)}
                r={i === selected ? 6 : 4.5}
                fill={p.is_promotion ? PROMO : NORMAL}
                stroke={SURFACE}
                strokeWidth={2}
              />
            ))}

            <SvgText x={PAD.left} y={HEIGHT - 6} fontSize={11} fill={colors.muted} fontFamily={fonts.medium}>
              {shortDate(points[0].observed_at)}
            </SvgText>
            <SvgText x={width - PAD.right} y={HEIGHT - 6} fontSize={11} fill={colors.muted} textAnchor="end" fontFamily={fonts.medium}>
              {shortDate(points[points.length - 1].observed_at)}
            </SvgText>
          </Svg>
        )}
      </View>

      {/* Relevé sélectionné : la valeur d'abord, le contexte ensuite */}
      {sel && (
        <View style={styles.readout}>
          <View style={[styles.key, { backgroundColor: sel.is_promotion ? PROMO : NORMAL }]} />
          <Text style={styles.readoutPrice}>{money(sel.price)}</Text>
          <Text style={[type.small, { flex: 1 }]} numberOfLines={1}>
            {sel.chain} · {shortDate(sel.observed_at)}
            {sel.is_promotion ? " · promo" : ""}
          </Text>
        </View>
      )}

      <View style={styles.legend}>
        {hasPromo && (
          <>
            <View style={styles.legendItem}>
              <View style={[styles.key, { backgroundColor: NORMAL }]} />
              <Text style={type.tiny}>Prix normal</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.key, { backgroundColor: PROMO }]} />
              <Text style={type.tiny}>Promotion</Text>
            </View>
          </>
        )}
        {median != null && (
          <View style={styles.legendItem}>
            <View style={styles.lineKey} />
            <Text style={type.tiny}>Prix habituel {money(median)}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  readout: { flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.sm },
  readoutPrice: { fontFamily: fonts.display, fontSize: 20, color: colors.ink },
  key: { width: 9, height: 9, borderRadius: 5 },
  legend: { flexDirection: "row", flexWrap: "wrap", columnGap: space.lg, rowGap: space.xs, marginTop: space.xs },
  lineKey: { width: 14, height: 2, borderRadius: 1, backgroundColor: colors.inkSoft, opacity: 0.7 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
});
