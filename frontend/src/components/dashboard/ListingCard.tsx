import { Card } from "@/components/ui/card";
import { MapPin, Home, MoreVertical, ExternalLink, Loader2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface Listing {
  id: string;
  title: string;
  price: number;
  area: number;
  location: string;
  furnished: string;
  availableFrom: string;
  pets: boolean;
  deposit: number;
  serviceCosts: number;
  postedAgo: string;
  imageUrl: string;
  externalUrl: string;
}

interface ListingCardProps {
  listing: Listing;
  onApply: () => void;
  isPending?: boolean;
}

export const ListingCard = ({ listing, onApply, isPending = false }: ListingCardProps) => {
  return (
    <Card className="glass overflow-hidden smooth-hover hover:scale-[1.02] group relative h-[300px]">
      {/* Image Background */}
      <div 
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: `url(${listing.imageUrl})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-black/20" />
      </div>

      {/* Three Dots Menu - Top Right */}
      <div className="absolute top-3 right-3 z-10">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full bg-background/20 backdrop-blur-sm hover:bg-background/40 text-white"
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <a
                href={listing.externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 cursor-pointer"
              >
                <ExternalLink className="h-4 w-4" />
                <span>View on website</span>
              </a>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Info Widgets - Bottom */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex items-end justify-between gap-2">
        {/* Small info widgets */}
        <div className="flex items-end gap-2">
          <div className="glass glass-dark rounded-md px-2 py-1.5 backdrop-blur-md">
            <span className="text-lg font-bold text-white">€{listing.price}</span>
          </div>
          <div className="glass glass-dark rounded-md px-2 py-1.5 backdrop-blur-md">
            <div className="flex items-center gap-1 text-white/90 text-xs">
              <Home className="h-3 w-3" />
              <span>{listing.area} m²</span>
            </div>
          </div>
          <div className="glass glass-dark rounded-md px-2 py-1.5 backdrop-blur-md">
            <div className="flex items-center gap-1 text-white/90 text-xs">
              <MapPin className="h-3 w-3" />
              <span>{listing.location.split(',')[0]}</span>
            </div>
          </div>
        </div>
        
        {/* Apply button or Pending badge */}
        {isPending ? (
          <Badge variant="secondary" className="h-8 px-3 glass glass-dark">
            <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
            <span>Pending</span>
          </Badge>
        ) : (
          <Button
            onClick={onApply}
            size="sm"
            className="smooth-hover hover:scale-105 h-8"
          >
            Apply
          </Button>
        )}
      </div>
    </Card>
  );
};
"contributed to this project in the UI and agentic parts, my code was uploaded by my friends - I had some git issues that I couldnt resolve on time"
