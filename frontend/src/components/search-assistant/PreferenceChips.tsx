import { Badge } from "@/components/ui/badge";
import { MapPin, Euro, Home, Calendar } from "lucide-react";
import { Preferences } from "@/pages/SearchAssistant";

interface PreferenceChipsProps {
  preferences: Preferences;
}

const PreferenceChips = ({ preferences }: PreferenceChipsProps) => {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-muted-foreground">Your Preferences:</p>
      <div className="flex flex-wrap gap-2">
        {preferences.location && (
          <Badge variant="secondary" className="glass glass-dark">
            <MapPin className="h-3 w-3 mr-1.5" />
            {preferences.location}
          </Badge>
        )}
        {preferences.budget && (
          <Badge variant="secondary" className="glass glass-dark">
            <Euro className="h-3 w-3 mr-1.5" />
            €{preferences.budget}/month
          </Badge>
        )}
        {preferences.bedrooms && (
          <Badge variant="secondary" className="glass glass-dark">
            <Home className="h-3 w-3 mr-1.5" />
            {preferences.bedrooms} bedrooms
          </Badge>
        )}
        {preferences.moveInDate && (
          <Badge variant="secondary" className="glass glass-dark">
            <Calendar className="h-3 w-3 mr-1.5" />
            {preferences.moveInDate}
          </Badge>
        )}
      </div>
    </div>
  );
};

export default PreferenceChips;
