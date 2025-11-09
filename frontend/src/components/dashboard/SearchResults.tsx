import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ChevronUp, MapPin, Home, Calendar, Trash2 } from "lucide-react";
import type { SearchCriteria } from "@/pages/Dashboard";
import { ListingCard } from "./ListingCard";
import { toast } from "sonner";

interface SearchResultsProps {
  search: SearchCriteria;
  onDelete: () => void;
}

// Mock listings data
const mockImages = [
  "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=80",
  "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800&q=80",
  "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=80",
  "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=800&q=80",
  "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=800&q=80",
  "https://images.unsplash.com/photo-1556912173-46c336c7fd55?w=800&q=80",
];

const generateMockListings = (criteria: SearchCriteria) => {
  const count = Math.floor(Math.random() * 8) + 3;
  return Array.from({ length: count }, (_, i) => ({
    id: `${criteria.id}-${i}`,
    title: `${criteria.housingType || "Apartment"} in ${criteria.city || "Amsterdam"}`,
    price: Math.floor(Math.random() * (criteria.priceRange[1] - criteria.priceRange[0])) + criteria.priceRange[0],
    area: Math.floor(Math.random() * (criteria.areaRange[1] - criteria.areaRange[0])) + criteria.areaRange[0],
    location: `${criteria.city || "Amsterdam"}, Netherlands`,
    furnished: criteria.furnishedStatus || "Furnished",
    availableFrom: criteria.availableDate ? criteria.availableDate.toLocaleDateString() : "Immediately",
    pets: criteria.petsAllowed,
    deposit: Math.floor(Math.random() * (criteria.depositRange[1] - criteria.depositRange[0])) + criteria.depositRange[0],
    serviceCosts: Math.floor(Math.random() * (criteria.serviceCostsRange[1] - criteria.serviceCostsRange[0])) + criteria.serviceCostsRange[0],
    postedAgo: "2 days ago",
    imageUrl: mockImages[i % mockImages.length],
    externalUrl: `https://example.com/listing/${criteria.id}-${i}`,
  }));
};

export const SearchResults = ({ search, onDelete }: SearchResultsProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [listings] = useState(() => generateMockListings(search));
  const [pendingListings, setPendingListings] = useState<Set<string>>(new Set());

  const handleApplyToAll = () => {
    toast.success(`Application initiated for all ${listings.length} listings`, {
      description: "AI agents will handle the applications automatically",
    });
  };

  const handleApply = (listingId: string) => {
    setPendingListings(prev => new Set([...prev, listingId]));
    toast.success("Application initiated", {
      description: "AI agent will handle the application",
    });
  };

  return (
    <Card className="glass glass-dark overflow-hidden animate-fade-in">
      <CardHeader className="cursor-pointer" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="flex items-center gap-2 mb-3">
              <Home className="h-5 w-5 text-primary" />
              Search Results
              <Badge variant="secondary">{listings.length} listings</Badge>
            </CardTitle>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 text-sm text-muted-foreground">
              {search.city && (
                <div className="flex items-center gap-1">
                  <MapPin className="h-4 w-4" />
                  <span>{search.city}</span>
                </div>
              )}
              {search.housingType && (
                <div className="flex items-center gap-1">
                  <Home className="h-4 w-4" />
                  <span>{search.housingType}</span>
                </div>
              )}
              <div>
                <span className="font-medium">€{search.priceRange[0]} - €{search.priceRange[1]}</span>
              </div>
              <div>
                <span>{search.areaRange[0]} - {search.areaRange[1]} m²</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="smooth-hover hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="smooth-hover">
              {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
            </Button>
          </div>
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          <div className="flex justify-between items-center pb-3 border-b">
            <span className="text-sm text-muted-foreground">
              Found {listings.length} matching properties
            </span>
            <Button
              onClick={handleApplyToAll}
              variant="default"
              size="sm"
              className="smooth-hover hover:scale-105"
            >
              Apply to All
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {listings.map((listing) => (
              <ListingCard
                key={listing.id}
                listing={listing}
                onApply={() => handleApply(listing.id)}
                isPending={pendingListings.has(listing.id)}
              />
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
};
