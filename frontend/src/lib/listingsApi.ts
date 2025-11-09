// src/lib/listingsApi.ts
const BACKEND = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface FetchListingsParams {
  location?: string;
  budget?: string | number;
  min_size?: number;
  bedrooms?: string;
  petFriendly?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  limit?: number;
}

export async function fetchListingsForPreferences(prefs: FetchListingsParams) {
  const params = new URLSearchParams();
  
  if (prefs.location) params.set("city", prefs.location);
  
  if (prefs.budget) {
    // normalize budget (strip € and commas)
    const digits = String(prefs.budget).replace(/[^0-9]/g, "");
    if (digits) params.set("max_price", digits);
  }
  
  if (prefs.min_size) params.set("min_area", String(prefs.min_size));
  
  if (prefs.lat !== undefined && prefs.lng !== undefined && prefs.radius_km !== undefined) {
    params.set("lat", String(prefs.lat));
    params.set("lng", String(prefs.lng));
    params.set("radius_km", String(prefs.radius_km));
  }
  
  const limit = prefs.limit ?? 50;
  params.set("limit", String(limit));

  const url = `${BACKEND}/listings?${params.toString()}`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) return { items: [], raw: null };
    const json = await res.json();
    return { items: json.items ?? [], raw: json };
  } catch (error) {
    console.error("fetchListingsForPreferences error:", error);
    return { items: [], raw: null };
  }
}

export async function fetchListingById(id: string) {
  const url = `${BACKEND}/listing/${encodeURIComponent(id)}`;
  
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch (error) {
    console.error("fetchListingById error:", error);
    return null;
  }
}

export async function applyForListing(
  userProfile: any,
  listingDetails: any
): Promise<{ success: boolean; job_id?: number; error?: string }> {
  const url = `${BACKEND}/agent/housing/apply`;
  
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_profile: userProfile,
        listing_details: listingDetails,
      }),
    });
    
    const data = await res.json();
    
    if (res.status === 202 && data.job_id) {
      return { success: true, job_id: data.job_id };
    }
    
    return { success: false, error: data.error || "Application failed" };
  } catch (error) {
    console.error("applyForListing error:", error);
    return { success: false, error: String(error) };
  }
}

// Utility to poll job once (for simple cases)
export async function pollJobOnce(jobId: number): Promise<any> {
  return new Promise<any>((resolve, reject) => {
    const tick = async () => {
      try {
        const r = await fetch(`${BACKEND}/jobs/status/${jobId}`);
        if (!r.ok) {
          setTimeout(tick, 1500);
          return;
        }
        const j = await r.json();
        if (j.status === "finished" || j.status === "error") {
          resolve(j);
        } else {
          setTimeout(tick, 1500);
        }
      } catch (e) {
        reject(e);
      }
    };
    tick();
  });
}
