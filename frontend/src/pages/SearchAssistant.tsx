import { useState } from "react";
import ChatInterface from "@/components/search-assistant/ChatInterface";
import MapView from "@/components/search-assistant/MapView";
import { Button } from "@/components/ui/button";
import { Home, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export interface Preferences {
  location?: string;
  budget?: string;
  minArea?: string; // Minimum area in m² (e.g., "50")
  bedrooms?: string;
  moveInDate?: string;
  furnished?: string;
  petFriendly?: string;
  session_id?: string;
  last_search_results?: any[];
}

const SearchAssistant = () => {
  const [preferences, setPreferences] = useState<Preferences>({});

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </Button>
            </Link>
            
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-primary/10">
                <Home className="h-5 w-5 text-primary" />
              </div>
              <span className="text-xl font-bold text-foreground">HomePilot AI</span>
            </div>
            
            <div className="w-20" /> {/* Spacer for alignment */}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-[1fr,1.2fr] gap-6 h-[calc(100vh-140px)]">
          {/* Chat Section */}
          <div className="flex flex-col">
            <ChatInterface 
              onPreferencesUpdate={setPreferences}
              preferences={preferences}
            />
          </div>

          {/* Map Section */}
          <div className="flex flex-col">
            <MapView preferences={preferences} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default SearchAssistant;
