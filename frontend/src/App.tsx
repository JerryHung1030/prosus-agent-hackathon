import { useState } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import Dashboard from "./pages/Dashboard";
import SearchAssistant from "./pages/SearchAssistant";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const Banner = () => {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;

  return (
    <div className="fixed top-0 left-0 w-full z-50 bg-yellow-100 border-b border-yellow-300 text-black text-sm py-2 px-4 flex justify-between items-center">
      <span>
        Please ensure no other instances of this webpage are open on your device.
        This app relies on a cache limited to one active tab.
      </span>
      <button
        onClick={() => setVisible(false)}
        className="text-black text-lg font-bold leading-none px-2"
        aria-label="Close banner"
      >
        ×
      </button>
    </div>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <Banner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/search-assistant" element={<SearchAssistant />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
