import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  StatusBar,
  Image,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { Ionicons } from "@expo/vector-icons";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://192.168.1.100:8000";
const USER_ID = "demo-user-mobile";
const DEMO_MODE = true;
const DEMO_COORDS = {
  latitude: 48.8566,
  longitude: 2.3522,
};

type Product = { id:number; ean:string; name:string; brand?:string; quantity?:string; image_url?:string };
type Store = { id:number; chain:string; name:string; address:string; city:string; latitude:number; longitude:number; distance_km?:number };
type ComparisonRow = { observation_id:number; store_id:number; store_name:string; chain:string; price:number; is_promotion:boolean; promotion_label?:string; observed_at:string; distance_km?:number; confirmations:number; rejections:number; confidence:number; rank:number; savings_vs_best:number };
type Comparison = { product:Product; results:ComparisonRow[]; best_price?:number; store_count:number };

const money=(n:number)=>`${n.toFixed(2).replace('.',',')} €`;
const freshness=(iso:string)=>{const h=(Date.now()-new Date(iso).getTime())/36e5; if(h<6)return "Très récent"; if(h<24)return "Aujourd’hui"; if(h<72)return "Récent"; return "À vérifier"};

export default function App(){
  const [permission,requestPermission]=useCameraPermissions();
  const [scanning,setScanning]=useState(false);
  const barcodeLocked = useRef(false);
  const [ean,setEan]=useState("");
  const [product,setProduct]=useState<Product|null>(null);
  const [comparison,setComparison]=useState<Comparison|null>(null);
  const [loading,setLoading]=useState(false);
  const [coords,setCoords]=useState({latitude:48.8566,longitude:2.3522});
  const [locationReady,setLocationReady]=useState(false);
  const [contribute,setContribute]=useState(false);
  const [stores,setStores]=useState<Store[]>([]);
  const [selectedStore,setSelectedStore]=useState<Store|null>(null);
  const [price,setPrice]=useState("");
  const [promo,setPromo]=useState(false);
  const [promoLabel,setPromoLabel]=useState("");
  const [saving,setSaving]=useState(false);
  const api=useMemo(()=>API_URL.replace(/\/$/,""),[]);
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const [suggestionModal, setSuggestionModal] = useState(false);

  useEffect(() => {
    (async () => {
      if (DEMO_MODE) {
        setCoords(DEMO_COORDS);
        setLocationReady(false);
        return;
      }

      const p = await Location.requestForegroundPermissionsAsync();

      if (p.status === "granted") {
        try {
          const l = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.Balanced,
          });

          setCoords({
            latitude: l.coords.latitude,
            longitude: l.coords.longitude,
          });

          setLocationReady(true);
        } catch {}
      }
    })();
  }, []);
  
 async function searchProduct(code: string) {
    const clean = code.trim();
    if (!clean) return;

    setLoading(true);
    setProduct(null);
    setComparison(null);
    setSuggestions([]);
    setSuggestionModal(false);

    try {
      const pr = await fetch(
        `${api}/products/${encodeURIComponent(clean)}`
      );

      if (!pr.ok) {
        // Produit exact introuvable → chercher des EAN proches
        const sr = await fetch(
          `${api}/products/${encodeURIComponent(clean)}/suggestions`
        );

        if (!sr.ok) {
          throw new Error("Produit introuvable.");
        }

        const suggested = await sr.json();

        if (suggested.length > 0) {
          setSuggestions(suggested);
          setSuggestionModal(true);
          return;
        }

        throw new Error(
          `Produit introuvable.\nCode détecté : ${clean}`
        );
      }

      const p = await pr.json();
      setProduct(p);

      const cr = await fetch(
        `${api}/products/${encodeURIComponent(clean)}/comparison?latitude=${coords.latitude}&longitude=${coords.longitude}&radius_km=10`
      );

      if (!cr.ok) {
        throw new Error("Les prix n'ont pas pu être chargés.");
      }

      setComparison(await cr.json());

    } catch (e) {
      Alert.alert(
        "Impossible de continuer",
        e instanceof Error ? e.message : "Erreur réseau."
      );
    } finally {
      setLoading(false);
    }
  }

  async function onBarcodeScanned({ data }: { data: string }) {
    if (barcodeLocked.current) return;

    barcodeLocked.current = true;

    console.log("BARCODE DETECTED :", data);

    setScanning(false);
    setEan(data);

    await searchProduct(data);

    setTimeout(() => {
      barcodeLocked.current = false;
    }, 1000);
  }

  async function vote(id:number,value:1|-1){try{const r=await fetch(`${api}/observations/${id}/vote`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:USER_ID,vote:value})});if(!r.ok)throw new Error();if(ean)await searchProduct(ean)}catch{Alert.alert("Erreur","Ton vote n’a pas pu être envoyé.")}}
  async function openContribution(){
    try{const r=await fetch(`${api}/stores/nearby?latitude=${coords.latitude}&longitude=${coords.longitude}&radius_km=15`);if(!r.ok)throw new Error();const list=await r.json();setStores(list);setSelectedStore(list[0]??null);setContribute(true)}catch{Alert.alert("Magasins indisponibles","Impossible de charger les magasins proches.")}
  }
  async function submitObservation(){
    if(!product||!selectedStore||!price)return Alert.alert("Il manque une information","Choisis un magasin et indique le prix.");
    setSaving(true);try{const r=await fetch(`${api}/observations`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ean:product.ean,store_id:selectedStore.id,price:Number(price.replace(',','.')),is_promotion:promo,promotion_label:promo?promoLabel||"Promotion":null,user_id:USER_ID,latitude:coords.latitude,longitude:coords.longitude})});const body=await r.json();if(!r.ok)throw new Error(body.detail||"Erreur");setContribute(false);setPrice("");setPromo(false);setPromoLabel("");Alert.alert("Prix ajouté ✓","Merci ! La communauté pourra maintenant le confirmer.");await searchProduct(product.ean)}catch(e){Alert.alert("Prix non envoyé",e instanceof Error?e.message:"Erreur")}finally{setSaving(false)}
  }

  if (scanning) {
  return (
      <View style={styles.camera}>
        <CameraView
          key="barcode-camera"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
          }}
          facing="back"
          active={true}
          onBarcodeScanned={onBarcodeScanned}
          barcodeScannerSettings={{
            barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"],
          }}
        />

        <SafeAreaView style={styles.cameraUI}>
          <View style={styles.cameraTop}>
            <TouchableOpacity
              onPress={() => setScanning(false)}
              style={styles.round}
            >
              <Ionicons name="close" size={26} color="#fff" />
            </TouchableOpacity>

            <Text style={styles.cameraTitle}>Scanner</Text>
            <View style={{ width: 44 }} />
          </View>

          <View style={styles.target}>
            <View style={styles.cornerTL} />
            <View style={styles.cornerTR} />
            <View style={styles.cornerBL} />
            <View style={styles.cornerBR} />
          </View>

          <View style={styles.cameraBottom}>
            <Text style={styles.cameraHint}>
              Place le code-barres dans le cadre
            </Text>
            <Text style={styles.cameraSub}>
              Le produit sera recherché automatiquement
            </Text>
          </View>
        </SafeAreaView>
      </View>
    );
  }
  return <SafeAreaView style={styles.safe}><StatusBar barStyle="dark-content"/><ScrollView contentContainerStyle={styles.container}>
    <View style={styles.header}><View><Text style={styles.eyebrow}>GROCERY WAZE</Text><Text style={styles.heading}>Trouve le bon prix.</Text></View><View style={styles.locationPill}><Ionicons name="location" size={14} color="#247a55"/><Text style={styles.locationText}>{locationReady?"Position active":"Position démo"}</Text></View></View>
    <Text style={styles.intro}>Scanne un produit et compare les prix relevés autour de toi.</Text>

    <TouchableOpacity style={styles.scanHero} onPress={async()=>{if(!permission?.granted){const r=await requestPermission();if(!r.granted)return}setScanning(true)}} activeOpacity={.9}><View style={styles.scanIcon}><Ionicons name="barcode-outline" size={32} color="#fff"/></View><View style={{flex:1}}><Text style={styles.scanTitle}>Scanner un produit</Text><Text style={styles.scanSub}>EAN-13, EAN-8 ou UPC</Text></View><Ionicons name="chevron-forward" size={24} color="#fff"/></TouchableOpacity>

    <View style={styles.manual}><Text style={styles.sectionLabel}>Recherche manuelle</Text><View style={styles.searchRow}><Ionicons name="search" size={20} color="#8a919a"/><TextInput value={ean} onChangeText={setEan} placeholder="Ex. 3017620422003" keyboardType="numeric" style={styles.searchInput}/><TouchableOpacity onPress={()=>searchProduct(ean)}><Text style={styles.searchAction}>Chercher</Text></TouchableOpacity></View></View>

    {loading&&<View style={styles.loading}><ActivityIndicator/><Text style={styles.muted}>Recherche des prix autour de toi…</Text></View>}

    {product&&<View style={styles.productCard}>{product.image_url?<Image source={{uri:product.image_url}} style={styles.productImage}/>:<View style={styles.productPlaceholder}><Ionicons name="cube-outline" size={28} color="#8a919a"/></View>}<View style={{flex:1}}><Text style={styles.productName}>{product.name}</Text><Text style={styles.productMeta}>{product.brand||"Marque inconnue"}{product.quantity?` · ${product.quantity}`:""}</Text><Text style={styles.productEan}>EAN {product.ean}</Text></View></View>}

    {comparison&&comparison.results.length>0&&<>
    {/* HEADER COMPARAISON */}
    <View style={styles.compareHeader}>
      <View>
        <Text style={styles.sectionTitle}>Meilleur prix près de toi</Text>
        <Text style={styles.muted}>
          {comparison.store_count} magasin{comparison.store_count>1?"s":""} comparé{comparison.store_count>1?"s":""}
        </Text>
      </View>

      <View style={styles.liveBadge}>
        <View style={styles.liveDot}/>
        <Text style={styles.liveBadgeText}>LIVE</Text>
      </View>
    </View>

    {/* MEILLEUR PRIX */}
    {comparison.results[0]&&(
        <View style={styles.bestPriceCard}>
          <View style={styles.bestPriceTop}>
            <View style={styles.bestLabelRow}>
              <View style={styles.bestIcon}>
                <Ionicons name="trophy" size={18} color="#9a6500"/>
              </View>

              <View>
                <Text style={styles.bestLabel}>MEILLEUR PRIX</Text>
                <Text style={styles.bestStore}>
                  {comparison.results[0].chain}
                </Text>
              </View>
            </View>

            <Text style={styles.heroPrice}>
              {money(comparison.results[0].price)}
            </Text>
          </View>

          <Text style={styles.bestStoreName}>
            {comparison.results[0].store_name}
          </Text>

          <View style={styles.bestMetaRow}>
            <View style={styles.metaItem}>
              <Ionicons
                name="navigate-outline"
                size={15}
                color="#247a55"
              />
              <Text style={styles.metaText}>
                {comparison.results[0].distance_km ?? "—"} km
              </Text>
            </View>

            <View style={styles.metaItem}>
              <Ionicons
                name="time-outline"
                size={15}
                color="#247a55"
              />
              <Text style={styles.metaText}>
                {freshness(comparison.results[0].observed_at)}
              </Text>
            </View>

            <View style={styles.metaItem}>
              <Ionicons
                name="shield-checkmark-outline"
                size={15}
                color="#247a55"
              />
              <Text style={styles.metaText}>
                {comparison.results[0].confidence}% fiable
              </Text>
            </View>
          </View>

          {comparison.results.length > 1 &&
            comparison.results[0].savings_vs_best === 0 && (
              <View style={styles.savingsBox}>
                <Ionicons
                  name="trending-down"
                  size={18}
                  color="#247a55"
                />

                <Text style={styles.savingsText}>
                  C’est actuellement le meilleur prix relevé autour de toi.
                </Text>
              </View>
            )}

          {comparison.results[0].is_promotion&&(
            <View style={styles.promoLarge}>
              <Ionicons
                name="pricetag"
                size={15}
                color="#9a6500"
              />

              <Text style={styles.promoText}>
                {comparison.results[0].promotion_label||"Promotion"}
              </Text>
            </View>
          )}
        </View>
      )}

      {/* AUTRES MAGASINS */}
      {comparison.results.length>1&&(
        <>
          <View style={styles.storesHeader}>
            <Text style={styles.sectionTitle}>Autres magasins</Text>
            <Text style={styles.muted}>
              du moins cher au plus cher
            </Text>
          </View>

          {comparison.results.slice(1).map((item,index)=>(
            <View
              key={item.observation_id}
              style={styles.storePriceCard}
            >
              <View style={styles.storeRank}>
                <Text style={styles.storeRankText}>
                  {index+2}
                </Text>
              </View>

              <View style={styles.storeInfo}>
                <View style={styles.storeTitleRow}>
                  <Text style={styles.chainSmall}>
                    {item.chain}
                  </Text>

                  {item.is_promotion&&(
                    <View style={styles.promoMini}>
                      <Ionicons
                        name="pricetag"
                        size={11}
                        color="#9a6500"
                      />
                      <Text style={styles.promoMiniText}>
                        PROMO
                      </Text>
                    </View>
                  )}
                </View>

                <Text style={styles.storeName}>
                  {item.store_name}
                </Text>

                <View style={styles.storeMetaRow}>
                  <Ionicons
                    name="navigate-outline"
                    size={13}
                    color="#8a919a"
                  />

                  <Text style={styles.storeMeta}>
                    {item.distance_km ?? "—"} km
                  </Text>

                  <Text style={styles.storeSeparator}>·</Text>

                  <Text style={styles.storeMeta}>
                    {freshness(item.observed_at)}
                  </Text>
                </View>
              </View>

              <View style={styles.storePriceBlock}>
                <Text style={styles.storePrice}>
                  {money(item.price)}
                </Text>

                {item.savings_vs_best>0&&(
                  <Text style={styles.moreExpensive}>
                    +{money(item.savings_vs_best)}
                  </Text>
                )}
              </View>
            </View>
          ))}
        </>
      )}

      {/* CONTRIBUTION */}
      <TouchableOpacity
        style={styles.contributeButton}
        onPress={openContribution}
        activeOpacity={0.85}
      >
        <View style={styles.contributeIcon}>
          <Ionicons
            name="add"
            size={20}
            color="#fff"
          />
        </View>

        <View style={{flex:1}}>
          <Text style={styles.contributeText}>
            J’ai trouvé un autre prix
          </Text>

          <Text style={styles.contributeSub}>
            Aide la communauté à garder les prix à jour
          </Text>
        </View>

        <Ionicons
          name="chevron-forward"
          size={20}
          color="#fff"
        />
      </TouchableOpacity>

      {/* VÉRIFICATION COMMUNAUTAIRE */}
      <View style={styles.communityCheck}>
        <View style={styles.communityCheckIcon}>
          <Ionicons
            name="people-outline"
            size={19}
            color="#247a55"
          />
        </View>

        <View style={{flex:1}}>
          <Text style={styles.communityCheckTitle}>
            Prix vérifiés par la communauté
          </Text>

          <Text style={styles.communityCheckText}>
            Les relevés peuvent être confirmés ou signalés
            par d’autres utilisateurs.
          </Text>
        </View>
      </View>
    </>}

    {comparison&&comparison.results.length===0&&<View style={styles.empty}><View style={styles.emptyIcon}><Ionicons name="storefront-outline" size={30} color="#247a55"/></View><Text style={styles.emptyTitle}>Aucun prix autour de toi</Text><Text style={styles.mutedCenter}>Tu peux être la première personne à relever ce produit.</Text><TouchableOpacity style={styles.darkButton} onPress={openContribution}><Text style={styles.darkButtonText}>Ajouter un prix</Text></TouchableOpacity></View>}

    <View style={styles.community}><View style={styles.communityIcon}><Ionicons name="people-outline" size={23} color="#247a55"/></View><View style={{flex:1}}><Text style={styles.communityTitle}>Prix communautaires</Text><Text style={styles.muted}>Chaque relevé est daté, localisé et peut être confirmé par d’autres utilisateurs.</Text></View></View>
  </ScrollView>
  <Modal
    visible={suggestionModal}
    animationType="slide"
    transparent
    onRequestClose={() => setSuggestionModal(false)}
  >
    <View style={styles.modalBackdrop}>
      <View style={styles.sheet}>

        <View style={styles.sheetHeader}>
          <View>
            <Text style={styles.sheetTitle}>
              Produit introuvable
            </Text>
            <Text style={styles.muted}>
              Voici des produits dont le code-barres ressemble
              à celui détecté.
            </Text>
          </View>

          <TouchableOpacity
            onPress={() => setSuggestionModal(false)}
            style={styles.closeSheet}
          >
            <Ionicons name="close" size={22} />
          </TouchableOpacity>
        </View>

        {suggestions.map((item) => (
          <TouchableOpacity
            key={item.id}
            onPress={() => {
              setSuggestionModal(false);
              searchProduct(item.ean);
            }}
            style={styles.suggestionCard}
          >
            {item.image_url ? (
              <Image
                source={{ uri: item.image_url }}
                style={styles.suggestionImage}
              />
            ) : (
              <View style={styles.suggestionPlaceholder}>
                <Ionicons
                  name="cube-outline"
                  size={24}
                  color="#8a919a"
                />
              </View>
            )}

            <View style={{ flex: 1 }}>
              <Text style={styles.suggestionName}>
                {item.name}
              </Text>

              <Text style={styles.suggestionMeta}>
                {item.brand || "Marque inconnue"}
                {item.quantity ? ` · ${item.quantity}` : ""}
              </Text>

              <Text style={styles.suggestionEan}>
                EAN {item.ean}
              </Text>
            </View>

            <Ionicons
              name="chevron-forward"
              size={20}
              color="#247a55"
            />
          </TouchableOpacity>
        ))}

        <TouchableOpacity
          style={styles.darkButton}
          onPress={() => setSuggestionModal(false)}
        >
          <Text style={styles.darkButtonText}>
            Aucun de ces produits
          </Text>
        </TouchableOpacity>

      </View>
    </View>
  </Modal>
  <Modal
    visible={contribute}
    animationType="slide"
    transparent
    onRequestClose={() => setContribute(false)}
  >
    <KeyboardAvoidingView
      style={styles.modalBackdrop}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={styles.sheetContribution}>

        <View style={styles.sheetHeader}>
          <View style={{flex:1}}>
            <Text style={styles.sheetTitle}>
              Ajouter un prix
            </Text>

            <Text style={styles.muted}>
              Pour {product?.name}
            </Text>
          </View>

          <TouchableOpacity
            onPress={() => setContribute(false)}
            style={styles.closeSheet}
          >
            <Ionicons name="close" size={22} />
          </TouchableOpacity>
        </View>

        <ScrollView
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{paddingBottom:20}}
        >

          <Text style={styles.fieldLabel}>
            Magasin
          </Text>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={{marginBottom:16}}
            keyboardShouldPersistTaps="handled"
          >
            {stores.map(s => (
              <TouchableOpacity
                key={s.id}
                onPress={() => setSelectedStore(s)}
                style={[
                  styles.storeChip,
                  selectedStore?.id === s.id &&
                    styles.storeChipActive
                ]}
              >
                <Text
                  style={[
                    styles.storeChipText,
                    selectedStore?.id === s.id &&
                      styles.storeChipTextActive
                  ]}
                >
                  {s.chain}
                </Text>

                <Text style={styles.chipDistance}>
                  {s.distance_km} km
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={styles.fieldLabel}>
            Prix affiché
          </Text>

          <View style={styles.priceInputRow}>
            <TextInput
              value={price}
              onChangeText={setPrice}
              placeholder="0,00"
              keyboardType="decimal-pad"
              style={styles.bigInput}
              returnKeyType="done"
            />

            <Text style={styles.euro}>€</Text>
          </View>

          <TouchableOpacity
            style={[
              styles.promoToggle,
              promo && styles.promoToggleActive
            ]}
            onPress={() => setPromo(!promo)}
          >
            <Ionicons
              name={promo ? "checkbox" : "square-outline"}
              size={22}
              color={promo ? "#9a6500" : "#7b8490"}
            />

            <Text style={styles.promoToggleText}>
              C’est une promotion
            </Text>
          </TouchableOpacity>

          {promo && (
            <TextInput
              value={promoLabel}
              onChangeText={setPromoLabel}
              placeholder="Ex. -20%, carte fidélité..."
              style={styles.promoInput}
            />
          )}

          <View style={styles.locationNoteBox}>
            <Ionicons
              name="location"
              size={17}
              color="#247a55"
            />

            <Text style={styles.locationNote}>
              Position enregistrée pour vérifier que tu es
              proche du magasin.
            </Text>
          </View>

          <TouchableOpacity
            style={styles.submit}
            onPress={submitObservation}
            disabled={saving}
            activeOpacity={0.85}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.submitText}>
                Publier le prix
              </Text>
            )}
          </TouchableOpacity>

        </ScrollView>

      </View>
    </KeyboardAvoidingView>
  </Modal>
  </SafeAreaView>
}

const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:"#f5f7f6"},container:{padding:20,paddingBottom:40},
  header:{flexDirection:"row",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8},eyebrow:{fontSize:12,fontWeight:"900",letterSpacing:1.6,color:"#247a55"},heading:{fontSize:29,fontWeight:"900",color:"#171a1f",marginTop:3},intro:{color:"#667085",fontSize:15,lineHeight:22,marginBottom:18,maxWidth:350},
  locationPill:{flexDirection:"row",alignItems:"center",gap:4,backgroundColor:"#e8f7ef",paddingHorizontal:10,paddingVertical:7,borderRadius:20},locationText:{fontSize:11,fontWeight:"800",color:"#247a55"},
  scanHero:{backgroundColor:"#247a55",borderRadius:20,padding:17,flexDirection:"row",alignItems:"center",gap:14,shadowOpacity:.12,shadowRadius:12,shadowOffset:{width:0,height:6},marginBottom:18},scanIcon:{width:54,height:54,borderRadius:16,backgroundColor:"#ffffff22",alignItems:"center",justifyContent:"center"},scanTitle:{fontSize:18,fontWeight:"900",color:"#fff"},scanSub:{color:"#d8f1e5",marginTop:2},
  manual:{marginBottom:18},sectionLabel:{fontSize:12,fontWeight:"900",textTransform:"uppercase",letterSpacing:.7,color:"#7b8490",marginBottom:8},searchRow:{height:50,backgroundColor:"#fff",borderWidth:1,borderColor:"#e5e7eb",borderRadius:14,flexDirection:"row",alignItems:"center",paddingHorizontal:14,gap:9},searchInput:{flex:1,fontSize:15,color:"#171a1f"},searchAction:{fontWeight:"900",color:"#247a55"},loading:{alignItems:"center",gap:8,paddingVertical:20},muted:{color:"#667085",fontSize:13,lineHeight:19},
  productCard:{backgroundColor:"#fff",borderRadius:18,padding:14,flexDirection:"row",gap:14,marginBottom:20,borderWidth:1,borderColor:"#e6e9eb"},productImage:{width:72,height:72,borderRadius:12},productPlaceholder:{width:72,height:72,borderRadius:12,backgroundColor:"#eef1f0",alignItems:"center",justifyContent:"center"},productName:{fontSize:17,fontWeight:"900",color:"#171a1f",lineHeight:22},productMeta:{fontSize:13,color:"#667085",marginTop:3},productEan:{fontSize:11,color:"#9aa1aa",marginTop:7},
  resultHeader:{flexDirection:"row",justifyContent:"space-between",alignItems:"center",marginBottom:10},sectionTitle:{fontSize:21,fontWeight:"900",color:"#171a1f"},bestBadge:{flexDirection:"row",gap:5,alignItems:"center",backgroundColor:"#e8f7ef",borderRadius:999,paddingHorizontal:9,paddingVertical:6},bestBadgeText:{fontSize:9,fontWeight:"900",color:"#247a55"},
  priceCard:{backgroundColor:"#fff",borderRadius:18,padding:16,marginBottom:11,borderWidth:1,borderColor:"#e6e9eb"},bestCard:{borderColor:"#b8dfca",borderWidth:1.5},priceTop:{flexDirection:"row",justifyContent:"space-between",gap:10},storeLine:{flexDirection:"row",alignItems:"center",gap:7},crown:{width:22,height:22,borderRadius:7,backgroundColor:"#fff2c9",alignItems:"center",justifyContent:"center"},chain:{fontWeight:"900",fontSize:16,color:"#171a1f"},storeName:{fontSize:12,color:"#667085",marginTop:2},distance:{fontSize:11,color:"#7b8490",marginTop:5},price:{fontSize:24,fontWeight:"900",color:"#171a1f"},bestPrice:{color:"#247a55",fontSize:28},moreExpensive:{fontSize:11,color:"#b42318",marginTop:2},
  promo:{marginTop:12,backgroundColor:"#fff6df",borderRadius:9,padding:8,flexDirection:"row",gap:6,alignItems:"center",alignSelf:"flex-start"},promoText:{fontSize:12,fontWeight:"800",color:"#9a6500"},confRow:{flexDirection:"row",alignItems:"center",gap:9,marginTop:13},confTrack:{height:6,backgroundColor:"#edf0ee",borderRadius:10,flex:1,overflow:"hidden"},confFill:{height:6,backgroundColor:"#247a55",borderRadius:10},confText:{fontSize:11,fontWeight:"800",color:"#247a55",width:73,textAlign:"right"},
  voteRow:{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginTop:12,paddingTop:11,borderTopWidth:1,borderTopColor:"#f0f1f2"},votes:{fontSize:11,color:"#7b8490"},voteButtons:{flexDirection:"row",gap:6},vote:{flexDirection:"row",alignItems:"center",gap:4,backgroundColor:"#f5f6f6",paddingHorizontal:9,paddingVertical:7,borderRadius:9},
  empty:{backgroundColor:"#fff",borderRadius:18,padding:22,alignItems:"center",borderWidth:1,borderColor:"#e6e9eb",marginBottom:15},emptyIcon:{width:58,height:58,borderRadius:18,backgroundColor:"#e8f7ef",alignItems:"center",justifyContent:"center",marginBottom:10},emptyTitle:{fontSize:17,fontWeight:"900",marginBottom:4},mutedCenter:{color:"#667085",textAlign:"center",lineHeight:19},darkButton:{marginTop:15,backgroundColor:"#171a1f",paddingHorizontal:18,paddingVertical:11,borderRadius:11},darkButtonText:{color:"#fff",fontWeight:"900"},
  community:{flexDirection:"row",gap:12,backgroundColor:"#eef7f1",padding:15,borderRadius:16,marginTop:18},communityIcon:{width:40,height:40,borderRadius:12,backgroundColor:"#d7eddf",alignItems:"center",justifyContent:"center"},communityTitle:{fontWeight:"900",fontSize:14,color:"#247a55",marginBottom:2},
  camera:{flex:1,backgroundColor:"#000"},cameraUI:{flex:1,justifyContent:"space-between"},cameraTop:{paddingHorizontal:18,paddingTop:10,flexDirection:"row",justifyContent:"space-between",alignItems:"center"},round:{width:44,height:44,borderRadius:22,backgroundColor:"#0009",alignItems:"center",justifyContent:"center"},cameraTitle:{color:"#fff",fontSize:18,fontWeight:"900"},target:{width:"78%",aspectRatio:1.7,alignSelf:"center",position:"relative"},cornerTL:{position:"absolute",left:0,top:0,width:35,height:35,borderLeftWidth:3,borderTopWidth:3,borderColor:"#fff",borderTopLeftRadius:10},cornerTR:{position:"absolute",right:0,top:0,width:35,height:35,borderRightWidth:3,borderTopWidth:3,borderColor:"#fff",borderTopRightRadius:10},cornerBL:{position:"absolute",left:0,bottom:0,width:35,height:35,borderLeftWidth:3,borderBottomWidth:3,borderColor:"#fff",borderBottomLeftRadius:10},cornerBR:{position:"absolute",right:0,bottom:0,width:35,height:35,borderRightWidth:3,borderBottomWidth:3,borderColor:"#fff",borderBottomRightRadius:10},cameraBottom:{backgroundColor:"#000b",padding:22,alignItems:"center"},cameraHint:{color:"#fff",fontSize:16,fontWeight:"900"},cameraSub:{color:"#bbb",marginTop:5},
  modalBackdrop:{flex:1,backgroundColor:"#0007",justifyContent:"flex-end"},sheet:{backgroundColor:"#fff",borderTopLeftRadius:26,borderTopRightRadius:26,padding:22,paddingBottom:32},sheetHeader:{flexDirection:"row",justifyContent:"space-between",alignItems:"center",marginBottom:20},sheetTitle:{fontSize:23,fontWeight:"900"},closeSheet:{width:38,height:38,borderRadius:19,backgroundColor:"#f1f2f3",alignItems:"center",justifyContent:"center"},fieldLabel:{fontSize:12,fontWeight:"900",color:"#667085",textTransform:"uppercase",letterSpacing:.6,marginBottom:8},storeChip:{borderWidth:1,borderColor:"#e1e5e3",borderRadius:12,padding:10,marginRight:8,minWidth:105},storeChipActive:{borderColor:"#247a55",backgroundColor:"#e8f7ef"},storeChipText:{fontWeight:"900",fontSize:13},storeChipTextActive:{color:"#247a55"},chipDistance:{fontSize:10,color:"#7b8490",marginTop:3},priceInputRow:{height:64,borderWidth:1,borderColor:"#dfe3e1",borderRadius:14,flexDirection:"row",alignItems:"center",paddingHorizontal:15,marginBottom:13},bigInput:{fontSize:30,fontWeight:"900",flex:1},euro:{fontSize:24,fontWeight:"900",color:"#7b8490"},promoToggle:{flexDirection:"row",alignItems:"center",gap:9,paddingVertical:11},promoToggleActive:{backgroundColor:"#fff8e7",paddingHorizontal:10,borderRadius:10},promoToggleText:{fontWeight:"800"},promoInput:{height:48,borderWidth:1,borderColor:"#dfe3e1",borderRadius:12,paddingHorizontal:13,marginBottom:10},locationNote:{fontSize:11,color:"#667085",lineHeight:16},submit:{backgroundColor:"#247a55",height:52,borderRadius:14,alignItems:"center",justifyContent:"center",marginTop:12},submitText:{color:"#fff",fontWeight:"900",fontSize:15},
  suggestionCard:{backgroundColor: "#f8faf9",borderWidth: 1,borderColor: "#e3e8e5",borderRadius: 15, padding: 12, flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 9,},suggestionImage: {width: 58,height: 58,borderRadius: 10,backgroundColor: "#eef1f0",},suggestionPlaceholder: {width: 58,  height: 58,  borderRadius: 10,backgroundColor: "#eef1f0",  alignItems: "center",justifyContent: "center",},suggestionName: {  fontSize: 14,  fontWeight: "900",color: "#171a1f",},suggestionMeta: {  fontSize: 12,color: "#667085",  marginTop: 3,},suggestionEan: {  fontSize: 10,  color: "#9aa1aa",  marginTop: 4,},
  compareHeader:{
    flexDirection:"row",
    justifyContent:"space-between",
    alignItems:"center",
    marginBottom:12
  },

  liveBadge:{
    flexDirection:"row",
    alignItems:"center",
    gap:5,
    backgroundColor:"#eef7f1",
    paddingHorizontal:9,
    paddingVertical:6,
    borderRadius:999
  },

  liveDot:{
    width:6,
    height:6,
    borderRadius:3,
    backgroundColor:"#247a55"
  },

  liveBadgeText:{
    fontSize:9,
    fontWeight:"900",
    color:"#247a55",
    letterSpacing:.6
  },

  bestPriceCard:{
    backgroundColor:"#fff",
    borderRadius:22,
    padding:18,
    marginBottom:22,
    borderWidth:1.5,
    borderColor:"#b8dfca"
  },

  bestPriceTop:{
    flexDirection:"row",
    justifyContent:"space-between",
    alignItems:"center",
    gap:10
  },

  bestLabelRow:{
    flexDirection:"row",
    alignItems:"center",
    gap:10,
    flex:1
  },

  bestIcon:{
    width:42,
    height:42,
    borderRadius:13,
    backgroundColor:"#fff2c9",
    alignItems:"center",
    justifyContent:"center"
  },

  bestLabel:{
    fontSize:10,
    fontWeight:"900",
    color:"#247a55",
    letterSpacing:1
  },

  bestStore:{
    fontSize:14,
    fontWeight:"900",
    color:"#171a1f",
    marginTop:2
  },

  heroPrice:{
    fontSize:30,
    fontWeight:"900",
    color:"#247a55"
  },

  bestStoreName:{
    fontSize:13,
    color:"#667085",
    marginTop:10
  },

  bestMetaRow:{
    flexDirection:"row",
    flexWrap:"wrap",
    gap:12,
    marginTop:13
  },

  metaItem:{
    flexDirection:"row",
    alignItems:"center",
    gap:4
  },

  metaText:{
    fontSize:11,
    fontWeight:"800",
    color:"#667085"
  },

  savingsBox:{
    flexDirection:"row",
    alignItems:"center",
    gap:8,
    backgroundColor:"#eef7f1",
    borderRadius:11,
    padding:10,
    marginTop:14
  },

  savingsText:{
    flex:1,
    fontSize:11,
    lineHeight:16,
    color:"#247a55",
    fontWeight:"700"
  },

  promoLarge:{
    alignSelf:"flex-start",
    flexDirection:"row",
    alignItems:"center",
    gap:6,
    backgroundColor:"#fff6df",
    borderRadius:9,
    paddingHorizontal:9,
    paddingVertical:7,
    marginTop:12
  },

  storesHeader:{
    marginBottom:10
  },

  storePriceCard:{
    backgroundColor:"#fff",
    borderRadius:17,
    padding:14,
    marginBottom:9,
    borderWidth:1,
    borderColor:"#e6e9eb",
    flexDirection:"row",
    alignItems:"center",
    gap:11
  },

  storeRank:{
    width:30,
    height:30,
    borderRadius:10,
    backgroundColor:"#f1f3f2",
    alignItems:"center",
    justifyContent:"center"
  },

  storeRankText:{
    fontSize:12,
    fontWeight:"900",
    color:"#667085"
  },

  storeInfo:{
    flex:1,
    minWidth:0
  },

  storeTitleRow:{
    flexDirection:"row",
    alignItems:"center",
    gap:7
  },

  chainSmall:{
    fontSize:13,
    fontWeight:"900",
    color:"#171a1f"
  },

  storeMetaRow:{
    flexDirection:"row",
    alignItems:"center",
    gap:4,
    marginTop:5
  },

  storeMeta:{
    fontSize:10,
    color:"#8a919a"
  },

  storeSeparator:{
    color:"#c4c8cc",
    fontSize:10
  },

  storePriceBlock:{
    alignItems:"flex-end"
  },

  storePrice:{
    fontSize:20,
    fontWeight:"900",
    color:"#171a1f"
  },

  promoMini:{
    flexDirection:"row",
    alignItems:"center",
    gap:3,
    backgroundColor:"#fff6df",
    borderRadius:6,
    paddingHorizontal:5,
    paddingVertical:3
  },

  promoMiniText:{
    fontSize:8,
    fontWeight:"900",
    color:"#9a6500"
  },

  contributeButton:{
    backgroundColor:"#171a1f",
    borderRadius:17,
    padding:14,
    flexDirection:"row",
    alignItems:"center",
    gap:11,
    marginTop:5
  },

  contributeIcon:{
    width:38,
    height:38,
    borderRadius:12,
    backgroundColor:"#ffffff22",
    alignItems:"center",
    justifyContent:"center"
  },

  contributeText:{
    color:"#fff",
    fontWeight:"900",
    fontSize:14
  },

  contributeSub:{
    color:"#aeb4ba",
    fontSize:10,
    marginTop:3
  },

  communityCheck:{
    flexDirection:"row",
    alignItems:"center",
    gap:10,
    backgroundColor:"#eef7f1",
    padding:13,
    borderRadius:15,
    marginTop:13,
    marginBottom:5
  },

  communityCheckIcon:{
    width:36,
    height:36,
    borderRadius:11,
    backgroundColor:"#d7eddf",
    alignItems:"center",
    justifyContent:"center"
  },

  communityCheckTitle:{
    fontSize:12,
    fontWeight:"900",
    color:"#247a55"
  },

  communityCheckText:{
    fontSize:10,
    color:"#667085",
    lineHeight:15,
    marginTop:2
  },
  sheetContribution:{
  backgroundColor:"#fff",
  borderTopLeftRadius:26,
  borderTopRightRadius:26,
  padding:22,
  paddingBottom:10,
  maxHeight:"88%"
  },

  locationNoteBox:{
    flexDirection:"row",
    alignItems:"center",
    gap:8,
    backgroundColor:"#eef7f1",
    borderRadius:12,
    padding:11,
    marginTop:8
  },
});
