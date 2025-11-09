import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Send, Loader2, Bot, User } from "lucide-react";
import { Preferences } from "@/pages/SearchAssistant";
import PreferenceChips from "./PreferenceChips";
import { fetchListingsForPreferences, pollJobOnce } from "@/lib/listingsApi";

const BACKEND = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatInterfaceProps {
  onPreferencesUpdate: (prefs: Preferences) => void;
  preferences: Preferences;
}

const monthNames = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
];

// Heuristic: infer location straight from user input (e.g., "in Leiden or The Hague")
const inferLocationFromText = (text: string): string | undefined => {
  const inMatch = text.match(/\b(?:in|around|near|within)\s+([^,.!?]+)/i);
  if (inMatch) {
    const locs = inMatch[1]
      .replace(/\bthe\s+netherlands\b/i, '')
      .replace(/\b(city|area|region)\b/gi, '')
      .trim();
    if (locs) return locs;
  }
  return undefined;
};

const normalizeBudget = (raw: string) => {
  const digits = raw.replace(/[^0-9]/g, "");
  if (!digits) return undefined;
  const formatted = Number.parseInt(digits, 10).toLocaleString();
  return `€${formatted}`;
};

const parsePreferencesFromMessage = (text: string): Preferences => {
  const extracted: Preferences = {};
  const lowerText = text.toLowerCase();

  const location = inferLocationFromText(text);
  if (location) {
    extracted.location = location;
  }

  const budgetMatch = text.match(/(?:€|eur|euro|budget|max(?:imum)?|under|below|around|up to)\s*([0-9][0-9.,]*)/i)
    || text.match(/([0-9][0-9.,]*)\s*(?:€|eur|euro)/i);
  if (budgetMatch?.[1]) {
    const normalized = normalizeBudget(budgetMatch[1]);
    if (normalized) {
      extracted.budget = normalized;
    }
  }

  const bedroomsMatch = lowerText.match(/(\d+)\s*(?:bed|bedroom|bedrooms)/i);
  if (bedroomsMatch?.[1]) {
    extracted.bedrooms = bedroomsMatch[1];
  }

  const monthRegex = new RegExp(monthNames.join("|"), "i");
  const monthMatch = text.match(monthRegex);
  if (monthMatch?.[0]) {
    const capitalized = monthMatch[0].charAt(0).toUpperCase() + monthMatch[0].slice(1).toLowerCase();
    extracted.moveInDate = capitalized;
  } else if (/next month/i.test(text)) {
    extracted.moveInDate = "Next month";
  } else if (/as soon as possible|asap|immediately/i.test(text)) {
    extracted.moveInDate = "As soon as possible";
  }

  if (/unfurnished|bare|shell/i.test(lowerText)) {
    extracted.furnished = "Unfurnished";
  } else if (/semi[-\s]?furnished/i.test(lowerText)) {
    extracted.furnished = "Semi-furnished";
  } else if (/furnished/i.test(lowerText)) {
    extracted.furnished = "Furnished";
  }

  if (/no pets|not (?:pet|animal) friendly/i.test(lowerText)) {
    extracted.petFriendly = "No";
  } else if (/(?:pet|animal)[\w\s]*(?:friendly|allowed)/i.test(lowerText) || /dog|cat/i.test(lowerText)) {
    extracted.petFriendly = "Yes";
  }

  return extracted;
};

const formatList = (items: string[]) => {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
};

// Map backend criteria format to frontend preferences format
const mapBackendCriteriaToPreferences = (backendCriteria: any): Preferences => {
  const mapped: Preferences = {};
  
  // Map city -> location
  if (backendCriteria.city) {
    mapped.location = backendCriteria.city;
  }
  
  // Map max_price -> budget
  if (backendCriteria.max_price !== undefined && backendCriteria.max_price !== null) {
    const price = Number(backendCriteria.max_price);
    if (!isNaN(price)) {
      mapped.budget = `€${price.toLocaleString()}`;
    }
  }
  
  // Map min_size -> minArea
  if (backendCriteria.min_size !== undefined && backendCriteria.min_size !== null) {
    const size = Number(backendCriteria.min_size);
    if (!isNaN(size)) {
      mapped.minArea = String(size);
    }
  }
  
  // Keep any other fields that match (bedrooms, furnished, petFriendly, etc.)
  if (backendCriteria.bedrooms) mapped.bedrooms = String(backendCriteria.bedrooms);
  if (backendCriteria.furnished) mapped.furnished = backendCriteria.furnished;
  if (backendCriteria.petFriendly || backendCriteria.pet_friendly) {
    mapped.petFriendly = backendCriteria.petFriendly || backendCriteria.pet_friendly;
  }
  if (backendCriteria.moveInDate || backendCriteria.move_in_date) {
    mapped.moveInDate = backendCriteria.moveInDate || backendCriteria.move_in_date;
  }
  
  return mapped;
};

const generateAssistantResponse = (allPreferences: Preferences, newlyCaptured: Preferences) => {
  const acknowledgements: string[] = [];
  if (newlyCaptured.location) {
    acknowledgements.push(`I'll focus on places around ${newlyCaptured.location}.`);
  }
  if (newlyCaptured.budget) {
    acknowledgements.push(`I'll keep listings near ${newlyCaptured.budget}.`);
  }
  if (newlyCaptured.bedrooms) {
    acknowledgements.push(`Noted that you're after ${newlyCaptured.bedrooms} bedrooms.`);
  }
  if (newlyCaptured.moveInDate) {
    acknowledgements.push(`I'll prioritise homes available ${newlyCaptured.moveInDate}.`);
  }
  if (newlyCaptured.furnished) {
    acknowledgements.push(`I'll filter for ${newlyCaptured.furnished.toLowerCase()} options.`);
  }
  if (newlyCaptured.petFriendly) {
    acknowledgements.push(
      newlyCaptured.petFriendly.toLowerCase() === "yes"
        ? "I'll only show pet-friendly listings."
        : "I'll avoid places with pet restrictions."
    );
  }

  const missingDetails: string[] = [];
  if (!allPreferences.budget) missingDetails.push("budget");
  if (!allPreferences.bedrooms) missingDetails.push("bedroom count");
  if (!allPreferences.moveInDate) missingDetails.push("ideal move-in timing");
  if (!allPreferences.furnished) missingDetails.push("furnishing preference");
  if (!allPreferences.petFriendly) missingDetails.push("pet policy");

  const acknowledgementText = acknowledgements.join(" ").trim();

  if (missingDetails.length === 0) {
    return (
      acknowledgementText ||
      "I'm here to help refine the shortlist. Let me know if you want to adjust anything or explore another area."
    );
  }

  const askForDetails = `Share your ${formatList(missingDetails)} when you're ready so I can tighten the matches.`;

  return acknowledgementText ? `${acknowledgementText} ${askForDetails}` : askForDetails;
};

const ChatInterface = ({ onPreferencesUpdate, preferences }: ChatInterfaceProps) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "Hi! I'm here to help you find your perfect home in the Netherlands. Let's start - which city or area are you interested in?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  // Maintain session_id with localStorage persistence
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return (preferences as any)?.session_id || window.localStorage.getItem("chat_session_id");
    } catch (e) {
      console.warn("localStorage not available", e);
      return (preferences as any)?.session_id || null;
    }
  });
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((m) => [...m, userMessage]);
    setInput("");
    setIsLoading(true);

    // Quick local parse to keep UI responsive
    try {
      const extractedPrefs = parsePreferencesFromMessage(userMessage.content);
      if (Object.keys(extractedPrefs).length > 0) {
        onPreferencesUpdate({ ...preferences, ...extractedPrefs });
      }
    } catch (e) {
      console.warn("local parse failed", e);
    }

    try {
      // Always send session_id if we have one (use local state first, then preferences fallback)
      const body = {
        session_id: sessionId || (preferences as any).session_id || undefined,
        message: userMessage.content,
      };
      
      console.log("🔵 Sending message to /agent/housing/chat", { session_id: body.session_id, message_preview: userMessage.content.slice(0, 50) });

      const res = await fetch(`${BACKEND}/agent/housing/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json().catch(() => ({}));
      
      console.log("🟢 Response from /agent/housing/chat", { status: res.status, session_id: data.session_id, has_response: !!data.response });

      // Persist session_id if backend returns one
      if (data.session_id && data.session_id !== sessionId) {
        console.log("💾 Persisting new session_id:", data.session_id);
        setSessionId(data.session_id);
        try { 
          window.localStorage.setItem("chat_session_id", data.session_id); 
        } catch (e) {
          console.warn("Failed to save session_id to localStorage", e);
        }
        onPreferencesUpdate({ ...preferences, session_id: data.session_id });
      }

      // Agent unavailable -> fallback to listing endpoint, but keep conversation visible
      if (res.status === 503 || data.status === "agent_unavailable" || !res.ok) {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content:
              "Agent features are currently unavailable. I'll show local results; use the map filters or click 'Search' to load listings.",
          },
        ]);
        // fallback: call /listings with current preferences
        const lres = await fetchListingsForPreferences(preferences);
        onPreferencesUpdate({ ...preferences, last_search_results: lres.items ?? [] });
        setIsLoading(false);
        return;
      }

      // If agent started a background search, backend returns 202 with job_id
      if (res.status === 202 && data.job_id) {
        if (data.session_id) onPreferencesUpdate({ ...preferences, session_id: data.session_id });

        setMessages((m) => [
          ...m,
          { role: "assistant", content: data.response || "Search started — I'll let you know when it's done." },
        ]);

        // poll job to completion and load listings on finish
        const jobRes = await pollJobOnce(data.job_id);
        const listings = jobRes.result?.listings ?? [];
        onPreferencesUpdate({ ...preferences, last_search_results: listings, session_id: data.session_id });
        setMessages((m) => [...m, { role: "assistant", content: `Search finished — showing ${listings.length} results on the map.` }]);
        setIsLoading(false);
        return;
      }

      // Normal conversational reply with optional extracted_criteria
      if (data.response) {
        if (data.session_id) onPreferencesUpdate({ ...preferences, session_id: data.session_id });
        // If agent included criteria (defensive: accept extracted_criteria, expected_criteria, or criteria)
        const agentCriteria = data.extracted_criteria || data.expected_criteria || data.criteria || {};
        console.log('🔵 Agent criteria received (backend format):', agentCriteria);
        if (agentCriteria && Object.keys(agentCriteria).length > 0) {
          const mappedCriteria = mapBackendCriteriaToPreferences(agentCriteria);
          console.log('🟢 Mapped criteria (frontend format):', mappedCriteria);
          console.log('🗺️ Updating preferences to trigger map update');
          onPreferencesUpdate({ ...preferences, ...mappedCriteria });
        }

        setMessages((m) => [...m, { role: "assistant", content: data.response }]);

        // if agent returned listings inline (synchronous), use them too
        if (data.listings && Array.isArray(data.listings)) {
          onPreferencesUpdate({ ...preferences, last_search_results: data.listings });
        }
      } else {
        setMessages((m) => [...m, { role: "assistant", content: "No reply from agent." }]);
      }
    } catch (error) {
      console.error("sendMessage error", error);
      setMessages((m) => [...m, { role: "assistant", content: "Server error. Try again or use the map filters." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <Card className="flex flex-col h-full glass glass-dark">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex gap-3 ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {message.role === "assistant" && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <Bot className="h-5 w-5 text-primary" />
              </div>
            )}
            
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground"
              }`}
            >
              <p className="text-sm whitespace-pre-wrap animate-fade-in">
                {message.content}
                {message.role === "assistant" && index === messages.length - 1 && !isLoading && message.content && (
                  <span className="inline-block w-0.5 h-4 bg-current ml-0.5 animate-pulse" />
                )}
              </p>
            </div>

            {message.role === "user" && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center">
                <User className="h-5 w-5 text-accent" />
              </div>
            )}
          </div>
        ))}
        
        {isLoading && (
          <div className="flex gap-3 justify-start">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div className="bg-secondary text-secondary-foreground rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message..."
            disabled={isLoading}
            className="flex-1"
          />
          <Button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            size="icon"
            className="flex-shrink-0"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </Card>
  );
};

export default ChatInterface;
