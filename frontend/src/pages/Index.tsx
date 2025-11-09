import { Button } from "@/components/ui/button";
import { Home, Search, FileCheck, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Decorative Background */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-accent/5 to-background pointer-events-none" />
        
        <div className="container mx-auto px-4 py-20 relative">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            {/* Logo/Brand */}
            <div className="inline-flex items-center gap-2 mb-4">
              <div className="p-3 rounded-xl bg-primary/10 backdrop-blur-sm">
                <Home className="h-8 w-8 text-primary" />
              </div>
              <span className="text-3xl font-bold text-foreground">HomePilot</span>
            </div>

            {/* Main Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight">
              Find your next home in the{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent">
                Netherlands
              </span>{" "}
              with HomePilot
            </h1>

            {/* Subheadline */}
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
              Automated housing search powered by AI. Set your criteria, and let our intelligent agents
              discover, apply, and track opportunities for you.
            </p>

            {/* CTA */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
              <Link to="/search-assistant">
                <Button size="lg" className="text-lg px-8 smooth-hover hover:scale-105 shadow-lg">
                  Start Searching
                  <Search className="ml-2 h-5 w-5" />
                </Button>
              </Link>
              <Button
                size="lg"
                variant="outline"
                className="text-lg px-8 smooth-hover hover:scale-105"
              >
                Learn More
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Process Section */}
      <section className="py-20 bg-secondary/30">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">How It Works</h2>
          
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {/* Step 1 */}
            <div className="glass glass-dark rounded-xl p-6 text-center smooth-hover hover:scale-105 hover:shadow-xl">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
                <Search className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-3">Discover</h3>
              <p className="text-muted-foreground">
                Set your search criteria: location, budget, size, and preferences. Our AI scans multiple
                platforms 24/7.
              </p>
            </div>

            {/* Step 2 */}
            <div className="glass glass-dark rounded-xl p-6 text-center smooth-hover hover:scale-105 hover:shadow-xl">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent/10 mb-4">
                <FileCheck className="h-8 w-8 text-accent" />
              </div>
              <h3 className="text-xl font-semibold mb-3">Apply</h3>
              <p className="text-muted-foreground">
                AI agents automatically apply to matching listings with personalized applications on your
                behalf.
              </p>
            </div>

            {/* Step 3 */}
            <div className="glass glass-dark rounded-xl p-6 text-center smooth-hover hover:scale-105 hover:shadow-xl">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
                <TrendingUp className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-3">Track</h3>
              <p className="text-muted-foreground">
                Monitor all your applications in one place. Get real-time updates and notifications on
                responses.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-3xl mx-auto text-center space-y-6">
            <h2 className="text-3xl font-bold">Why Choose HomePilot?</h2>
            <div className="grid sm:grid-cols-2 gap-6 text-left pt-8">
              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-primary/10 mt-1">
                    <div className="w-2 h-2 rounded-full bg-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">24/7 Monitoring</h4>
                    <p className="text-sm text-muted-foreground">
                      Never miss a new listing with round-the-clock automated searches
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-accent/10 mt-1">
                    <div className="w-2 h-2 rounded-full bg-accent" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Smart Filtering</h4>
                    <p className="text-sm text-muted-foreground">
                      Advanced criteria matching ensures you only see relevant properties
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-primary/10 mt-1">
                    <div className="w-2 h-2 rounded-full bg-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Instant Applications</h4>
                    <p className="text-sm text-muted-foreground">
                      Be the first to apply with automated, personalized responses
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-accent/10 mt-1">
                    <div className="w-2 h-2 rounded-full bg-accent" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Centralized Dashboard</h4>
                    <p className="text-sm text-muted-foreground">
                      Manage all your searches and applications in one clean interface
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-br from-primary/10 via-accent/5 to-background">
        <div className="container mx-auto px-4">
          <div className="max-w-3xl mx-auto text-center space-y-6">
            <h2 className="text-3xl font-bold">Ready to find your perfect home?</h2>
            <p className="text-xl text-muted-foreground">
              Join HomePilot today and let AI handle the hard work of house hunting.
            </p>
            <Link to="/search-assistant">
              <Button size="lg" className="text-lg px-8 smooth-hover hover:scale-105 shadow-lg">
                Get Started Now
                <Search className="ml-2 h-5 w-5" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="container mx-auto px-4">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <Home className="h-4 w-4 text-primary" />
              <span className="font-semibold">HomePilot</span>
            </div>
            <p>© 2024 HomePilot. Housing search made simple.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Index;
