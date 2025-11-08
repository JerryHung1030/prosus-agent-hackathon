import { useState } from "react";
import { SearchBuilder } from "@/components/dashboard/SearchBuilder";
import { SearchResults } from "@/components/dashboard/SearchResults";
import { Button } from "@/components/ui/button";
import { Home, Plus } from "lucide-react";
import { Link } from "react-router-dom";

export interface SearchCriteria {
  id: string;
  priceRange: [number, number];
  areaRange: [number, number];
  city: string;
  postTime: string;
  contractDuration: string;
  petsAllowed: boolean;
  depositRange: [number, number];
  serviceCostsRange: [number, number];
  housingType: string;
  furnishedStatus: string;
  availableDate: Date | undefined;
}

const Dashboard = () => {
  const [searches, setSearches] = useState<SearchCriteria[]>([]);
  const [showBuilder, setShowBuilder] = useState(false);

  const handleGenerateSearch = (criteria: SearchCriteria) => {
    setSearches([...searches, criteria]);
    setShowBuilder(false);
  };

  const handleDeleteSearch = (id: string) => {
    setSearches(searches.filter((s) => s.id !== id));
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="glass glass-dark border-b sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 smooth-hover hover:scale-105">
            <Home className="h-6 w-6 text-primary" />
            <span className="text-xl font-bold text-foreground">HomePilot</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground hidden sm:inline">
              {searches.length} active {searches.length === 1 ? "search" : "searches"}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {/* New Search Button */}
        {!showBuilder && (
          <div className="mb-8">
            <Button
              onClick={() => setShowBuilder(true)}
              size="lg"
              className="w-full sm:w-auto smooth-hover hover:scale-105"
            >
              <Plus className="h-5 w-5 mr-2" />
              New Search
            </Button>
          </div>
        )}

        {/* Search Builder */}
        {showBuilder && (
          <div className="mb-8 glass glass-dark rounded-xl p-6 animate-fade-in">
            <SearchBuilder
              onGenerate={handleGenerateSearch}
              onCancel={() => setShowBuilder(false)}
            />
          </div>
        )}

        {/* Active Searches */}
        <div className="space-y-6">
          {searches.length === 0 && !showBuilder && (
            <div className="text-center py-16">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-secondary mb-4">
                <Home className="h-10 w-10 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">No active searches</h3>
              <p className="text-muted-foreground mb-6">
                Create your first search to start finding homes in the Netherlands
              </p>
              <Button onClick={() => setShowBuilder(true)} size="lg" className="smooth-hover">
                <Plus className="h-5 w-5 mr-2" />
                Create Search
              </Button>
            </div>
          )}

          {searches.map((search) => (
            <SearchResults
              key={search.id}
              search={search}
              onDelete={() => handleDeleteSearch(search.id)}
            />
          ))}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
