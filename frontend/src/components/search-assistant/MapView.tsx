import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { APIProvider, Map, Marker } from "@vis.gl/react-google-maps";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Preferences } from "@/pages/SearchAssistant";
import { MapPin, RefreshCw, X } from "lucide-react";

interface MapViewProps {
  preferences: Preferences;
}

const GOOGLE_MAPS_API_KEY = "AIzaSyBWFfsY7vVUGNEtNLd9xT7gZfuOs3EBIPM";
const BACKEND_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const DEFAULT_CENTER = { lat: 52.3676, lng: 4.9041 }; // Amsterdam fallback
const COUNTRY_CONTEXT = "Netherlands";

type Coordinates = { lat: number; lng: number };

interface GeocodeResult {
  formatted_address?: string;
  geometry: { location: Coordinates };
  address_components?: Array<{ long_name: string; types: string[] }>;
}

interface ListingRecord extends Record<string, unknown> {
  id?: number;
  external_id?: string;
  url: string;
  title?: string;
  price_amount?: number;
  price_frequency?: string;
  area_m2?: number;
  street?: string;
  city?: string;
  postal_code?: string;
  housing_type?: string;
  furnishes?: string;
  agency_name?: string;
  agency_contact_url?: string;
  pets_allowed?: boolean | number | null;
  thumbnail_path?: string;
  location?: Coordinates | null;
  latitude?: number | null;
  longitude?: number | null;
  distance_km?: number | null;
}

interface ListingPin {
  lookupId: string;
  markerId: string;
  lat: number;
  lng: number;
  distanceKm?: number | null;
  summary: ListingRecord;
}

interface ParsedFilters {
  minPrice?: number;
  maxPrice?: number;
  petsAllowed?: boolean;
}

const parseBudget = (budget?: string): { min?: number; max?: number } => {
  if (!budget) return {};
  const numbers = (budget.match(/\d[\d.,]*/g) ?? [])
    .map((token) => Number(token.replace(/[.,]/g, "")))
    .filter(Number.isFinite);
  if (numbers.length === 0) {
    return {};
  }
  if (numbers.length === 1) {
    const normalized = budget.toLowerCase();
    if (/(min|min\.|from|above|over|starting)/.test(normalized)) {
      return { min: numbers[0] };
    }
    return { max: numbers[0] };
  }
  const [first, second] = numbers;
  return { min: Math.min(first, second), max: Math.max(first, second) };
};

const parsePetPreference = (preference?: string): boolean | undefined => {
  if (!preference) return undefined;
  const normalized = preference.toLowerCase();
  if (/(no|not|without|avoid)/.test(normalized)) return false;
  if (/(yes|allow|pet|cat|dog|friendly)/.test(normalized)) return true;
  return undefined;
};

const normalizePetsAllowed = (value: ListingRecord["pets_allowed"]): boolean | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value === 1;
  return null;
};

const resolveThumbnailUrl = (path?: string): string | undefined => {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path) || path.startsWith("data:")) {
    return path;
  }
  return `${BACKEND_BASE_URL}/${path.replace(/^\/+/, "")}`;
};

const formatPrice = (price?: number, frequency?: string) => {
  if (price === null || price === undefined) return null;
  const formatted = new Intl.NumberFormat("nl-NL", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(price);
  return frequency ? `${formatted} / ${frequency}` : formatted;
};

const formatDistance = (distanceKm?: number | null) => {
  if (distanceKm === null || distanceKm === undefined || Number.isNaN(distanceKm)) {
    return null;
  }
  if (distanceKm < 1) {
    return `${Math.round(distanceKm * 1000)} m away`;
  }
  return `${distanceKm.toFixed(1)} km away`;
};

const extractAreaLabel = (result: GeocodeResult): string | undefined => {
  const components = result.address_components ?? [];
  const priority = [
    "locality",
    "postal_town",
    "administrative_area_level_2",
    "administrative_area_level_1",
  ];
  for (const type of priority) {
    const match = components.find((component) => component.types.includes(type));
    if (match) return match.long_name;
  }
  return result.formatted_address;
};

const MapView = ({ preferences }: MapViewProps) => {
  const [mapCenter, setMapCenter] = useState<Coordinates>(DEFAULT_CENTER);
  const [mapZoom, setMapZoom] = useState(12);
  const [radiusKm, setRadiusKm] = useState(6);
  const [pins, setPins] = useState<ListingPin[]>([]);
  const [isPinsLoading, setIsPinsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedPin, setSelectedPin] = useState<ListingPin | null>(null);
  const [selectedListingDetails, setSelectedListingDetails] = useState<ListingRecord | null>(null);
  const [isListingDetailLoading, setIsListingDetailLoading] = useState(false);
  const [areaLabel, setAreaLabel] = useState<string>("Amsterdam");
  const [reloadToken, setReloadToken] = useState(0);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const listingControllerRef = useRef<AbortController | null>(null);

  const filters = useMemo<ParsedFilters>(() => {
    const budgetRange = parseBudget(preferences.budget);
    const petsAllowed = parsePetPreference(preferences.petFriendly);
    return {
      minPrice: budgetRange.min,
      maxPrice: budgetRange.max,
      petsAllowed,
    };
  }, [preferences.budget, preferences.petFriendly]);

  const updateRadius = useCallback((center: Coordinates, zoom: number) => {
    const containerWidth = mapContainerRef.current?.offsetWidth ?? window.innerWidth ?? 1024;
    const metersPerPixel = (156543.03392 * Math.cos((center.lat * Math.PI) / 180)) / 2 ** zoom;
    const radius = Math.max(0.25, (metersPerPixel * containerWidth * 0.5) / 1000);
    setRadiusKm(radius);
  }, []);

  useEffect(() => {
    updateRadius(mapCenter, mapZoom);
  }, [mapCenter, mapZoom, updateRadius]);

  useEffect(() => {
    if (!preferences.location) return;
    const tokens = preferences.location
      .split(/,| and | or /i)
      .map((item) => item.trim())
      .filter(Boolean);
    if (tokens.length === 0) return;

    const controller = new AbortController();
    const target = tokens[0];

    const geocode = async () => {
      try {
        const response = await fetch(
          `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(`${target}, ${COUNTRY_CONTEXT}`)}&key=${GOOGLE_MAPS_API_KEY}`,
          { signal: controller.signal },
        );
        const payload = await response.json();
        const result = (payload.results?.[0] ?? null) as GeocodeResult | null;
        if (!result) return;

        setMapCenter(result.geometry.location);
        const nextZoom = tokens.length > 1 ? 10 : 13;
        setMapZoom(nextZoom);
        updateRadius(result.geometry.location, nextZoom);
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Failed to geocode preferred location", error);
      }
    };

    void geocode();

    return () => controller.abort();
  }, [preferences.location, updateRadius]);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await fetch(
          `https://maps.googleapis.com/maps/api/geocode/json?latlng=${mapCenter.lat},${mapCenter.lng}&key=${GOOGLE_MAPS_API_KEY}`,
          { signal: controller.signal },
        );
        const payload = await response.json();
        const result = (payload.results?.[0] ?? null) as GeocodeResult | null;
        if (!result) return;
        const label = extractAreaLabel(result);
        if (label) {
          setAreaLabel(label);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("Failed to reverse geocode map center", error);
        }
      }
    }, 400);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [mapCenter.lat, mapCenter.lng]);

  useEffect(() => {
    listingControllerRef.current?.abort();
    const controller = new AbortController();
    listingControllerRef.current = controller;

    const { minPrice, maxPrice, petsAllowed } = filters;

    const timeoutId = window.setTimeout(async () => {
      setIsPinsLoading(true);
      setErrorMessage(null);
      try {
        const url = new URL(`${BACKEND_BASE_URL}/listings`);
        url.searchParams.set("lat", mapCenter.lat.toFixed(6));
        url.searchParams.set("lng", mapCenter.lng.toFixed(6));
        url.searchParams.set("radius", radiusKm.toFixed(2));
        url.searchParams.set("all", "true");
        if (minPrice !== undefined) {
          url.searchParams.set("min_price", String(Math.round(minPrice)));
        }
        if (maxPrice !== undefined) {
          url.searchParams.set("max_price", String(Math.round(maxPrice)));
        }
        if (petsAllowed !== undefined) {
          url.searchParams.set("pets_allowed", petsAllowed ? "true" : "false");
        }

        const response = await fetch(url.toString(), { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`Failed to fetch listings (${response.status})`);
        }

        const payload = (await response.json()) as { items?: ListingRecord[] };
        const items = Array.isArray(payload.items) ? payload.items : [];

        const nextPins = items
          .map((item) => {
            const location = item.location
              ? item.location
              : typeof item.latitude === "number" && typeof item.longitude === "number"
              ? { lat: item.latitude, lng: item.longitude }
              : null;
            const lookupId =
              item.id !== undefined && item.id !== null
                ? String(item.id)
                : typeof item.external_id === "string"
                ? item.external_id
                : null;
            if (!location || !lookupId) return null;
            const normalizedListing: ListingRecord = {
              ...item,
              location,
              pets_allowed: normalizePetsAllowed(item.pets_allowed),
            };
            const distance = typeof item.distance_km === "number" ? item.distance_km : null;
            return {
              lookupId,
              markerId: `${lookupId}-${location.lat.toFixed(5)}-${location.lng.toFixed(5)}`,
              lat: location.lat,
              lng: location.lng,
              distanceKm: distance,
              summary: {
                ...normalizedListing,
                distance_km: distance,
              },
            } as ListingPin;
          })
          .filter((value): value is ListingPin => value !== null);

        setPins(nextPins);
        setSelectedPin((prev) => {
          if (!prev) return null;
          return nextPins.find((pin) => pin.lookupId === prev.lookupId) ?? null;
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Error loading listings", error);
        setPins([]);
        setSelectedPin(null);
        setSelectedListingDetails(null);
        setErrorMessage("Unable to load listings for this area.");
      } finally {
        if (!controller.signal.aborted) {
          setIsPinsLoading(false);
        }
      }
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [filters, mapCenter.lat, mapCenter.lng, radiusKm, reloadToken]);

  const handleMarkerClick = useCallback(async (pin: ListingPin) => {
    setSelectedPin(pin);
    setSelectedListingDetails(null);
    setIsListingDetailLoading(true);
    try {
      const response = await fetch(`${BACKEND_BASE_URL}/listing/${encodeURIComponent(pin.lookupId)}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch listing detail (${response.status})`);
      }
      const detail = (await response.json()) as ListingRecord;
      setSelectedListingDetails({
        ...detail,
        pets_allowed: normalizePetsAllowed(detail.pets_allowed),
      });
    } catch (error) {
      console.error("Error fetching listing detail", error);
    } finally {
      setIsListingDetailLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  const detailToRender = selectedListingDetails ?? selectedPin?.summary ?? null;

  return (
    <Card className="h-full flex flex-col glass glass-dark">
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-lg">Available Listings</h3>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="glass glass-dark flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" />
              {areaLabel}
            </Badge>
            <Badge variant="secondary" className="glass glass-dark">
              Radius {radiusKm.toFixed(1)} km
            </Badge>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="glass glass-dark border border-border/60"
              onClick={handleRefresh}
              disabled={isPinsLoading}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isPinsLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            {isPinsLoading && (
              <Badge variant="outline" className="glass glass-dark animate-pulse">
                Loading...
              </Badge>
            )}
          </div>
        </div>
      </div>

      <div ref={mapContainerRef} className="flex-1 relative overflow-hidden">
        <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
          <Map
            center={mapCenter}
            zoom={mapZoom}
            gestureHandling="greedy"
            disableDefaultUI={false}
            mapId="housing-listings-map"
            onCameraChanged={(event) => {
              const nextCenter = event.detail.center;
              const nextZoom = event.detail.zoom;
              setMapCenter(nextCenter);
              setMapZoom(nextZoom);
              updateRadius(nextCenter, nextZoom);
            }}
          >
            {pins.map((pin) => (
              <Marker
                key={pin.markerId}
                position={{ lat: pin.lat, lng: pin.lng }}
                title={pin.summary.title ?? "Listing"}
                onClick={() => handleMarkerClick(pin)}
              />
            ))}
          </Map>
        </APIProvider>

        {errorMessage && (
          <Card className="absolute top-4 right-4 glass glass-dark px-3 py-2 text-xs text-muted-foreground max-w-xs border border-border/60">
            {errorMessage}
          </Card>
        )}

        {detailToRender && selectedPin && (
          <Card className="absolute bottom-6 left-6 max-w-md w-[320px] sm:w-[360px] p-4 glass glass-dark shadow-lg border border-border/60">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 text-primary" />
                  {detailToRender.city ?? areaLabel ?? "Selected Listing"}
                </div>
                <h4 className="mt-1 text-lg font-semibold leading-tight">
                  {detailToRender.title ?? "Listing"}
                </h4>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedPin(null);
                  setSelectedListingDetails(null);
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border/60 hover:bg-primary/20 transition"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {(() => {
              const thumbnailUrl = resolveThumbnailUrl(detailToRender.thumbnail_path as string | undefined);
              if (!thumbnailUrl) return null;
              return (
                <img
                  src={thumbnailUrl}
                  alt={detailToRender.title ?? "Listing thumbnail"}
                  className="mt-3 h-40 w-full rounded-lg object-cover border border-border/60"
                />
              );
            })()}

            <div className="mt-3 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-primary">
                  {
                    formatPrice(
                      detailToRender.price_amount as number | undefined,
                      detailToRender.price_frequency as string | undefined,
                    ) ?? "Price on request"
                  }
                </span>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {detailToRender.area_m2 && <span>{detailToRender.area_m2} m²</span>}
                  {formatDistance(detailToRender.distance_km) && (
                    <Badge variant="outline" className="glass glass-dark">
                      {formatDistance(detailToRender.distance_km)}
                    </Badge>
                  )}
                </div>
              </div>

              <div className="text-xs text-muted-foreground space-y-1">
                {detailToRender.street && <div>{detailToRender.street}</div>}
                {(detailToRender.postal_code || detailToRender.city) && (
                  <div>
                    {[detailToRender.postal_code, detailToRender.city].filter(Boolean).join(" " )}
                  </div>
                )}
                {detailToRender.pets_allowed !== null && detailToRender.pets_allowed !== undefined && (
                  <div>Pets {detailToRender.pets_allowed ? "allowed" : "not allowed"}</div>
                )}
              </div>

              <div className="flex items-center justify-between pt-2">
                <Button variant="secondary" size="sm" asChild className="glass glass-dark">
                  <a href={detailToRender.url} target="_blank" rel="noopener noreferrer">
                    View Listing
                  </a>
                </Button>
                {isListingDetailLoading && (
                  <Badge variant="outline" className="glass glass-dark animate-pulse">
                    Loading details…
                  </Badge>
                )}
              </div>
            </div>
          </Card>
        )}
      </div>
    </Card>
  );
};

export default MapView;
