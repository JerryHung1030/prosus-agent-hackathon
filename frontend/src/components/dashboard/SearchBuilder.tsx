import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { CalendarIcon, X } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import type { SearchCriteria } from "@/pages/Dashboard";

interface SearchBuilderProps {
  onGenerate: (criteria: SearchCriteria) => void;
  onCancel: () => void;
}

const DUTCH_CITIES = [
  "Amsterdam",
  "Rotterdam",
  "Utrecht",
  "Den Haag",
  "Eindhoven",
  "Groningen",
  "Tilburg",
  "Almere",
  "Breda",
  "Nijmegen",
];

const HOUSING_TYPES = [
  "Room",
  "Studio",
  "Apartment",
  "House",
  "Anti-squat",
  "Student residence",
];

const FURNISHED_STATUS = ["Furnished", "Partially furnished", "Unfurnished"];

const POST_TIME_OPTIONS = [
  { label: "Last 24 hours", value: "24h" },
  { label: "Last 3 days", value: "3d" },
  { label: "Last 7 days", value: "7d" },
  { label: "Last 14 days", value: "14d" },
  { label: "Last 30 days", value: "30d" },
];

export const SearchBuilder = ({ onGenerate, onCancel }: SearchBuilderProps) => {
  const [priceRange, setPriceRange] = useState<[number, number]>([500, 2000]);
  const [areaRange, setAreaRange] = useState<[number, number]>([20, 100]);
  const [city, setCity] = useState<string>("");
  const [postTime, setPostTime] = useState<string>("7d");
  const [contractDuration, setContractDuration] = useState<string>("");
  const [petsAllowed, setPetsAllowed] = useState(false);
  const [depositRange, setDepositRange] = useState<[number, number]>([0, 3000]);
  const [serviceCostsRange, setServiceCostsRange] = useState<[number, number]>([0, 300]);
  const [housingType, setHousingType] = useState<string>("");
  const [furnishedStatus, setFurnishedStatus] = useState<string>("");
  const [availableDate, setAvailableDate] = useState<Date>();

  const handleGenerate = () => {
    const criteria: SearchCriteria = {
      id: Date.now().toString(),
      priceRange,
      areaRange,
      city,
      postTime,
      contractDuration,
      petsAllowed,
      depositRange,
      serviceCostsRange,
      housingType,
      furnishedStatus,
      availableDate,
    };
    onGenerate(criteria);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">New Search</h2>
        <Button variant="ghost" size="icon" onClick={onCancel} className="smooth-hover">
          <X className="h-5 w-5" />
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Price Range */}
        <div className="space-y-3">
          <Label>Price Range (€/month)</Label>
          <div className="pt-2">
            <Slider
              value={priceRange}
              onValueChange={(value) => setPriceRange(value as [number, number])}
              min={0}
              max={5000}
              step={50}
              className="mb-2"
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>€{priceRange[0]}</span>
              <span>€{priceRange[1]}</span>
            </div>
          </div>
        </div>

        {/* Area Range */}
        <div className="space-y-3">
          <Label>Area (m²)</Label>
          <div className="pt-2">
            <Slider
              value={areaRange}
              onValueChange={(value) => setAreaRange(value as [number, number])}
              min={10}
              max={200}
              step={5}
              className="mb-2"
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>{areaRange[0]} m²</span>
              <span>{areaRange[1]} m²</span>
            </div>
          </div>
        </div>

        {/* City */}
        <div className="space-y-3">
          <Label>City</Label>
          <Select value={city} onValueChange={setCity}>
            <SelectTrigger>
              <SelectValue placeholder="Select city" />
            </SelectTrigger>
            <SelectContent className="pointer-events-auto bg-popover z-50">
              {DUTCH_CITIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Post Time */}
        <div className="space-y-3">
          <Label>Posted within</Label>
          <Select value={postTime} onValueChange={setPostTime}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="pointer-events-auto bg-popover z-50">
              {POST_TIME_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Contract Duration */}
        <div className="space-y-3">
          <Label>Min. Contract Duration (months)</Label>
          <Input
            type="number"
            value={contractDuration}
            onChange={(e) => setContractDuration(e.target.value)}
            placeholder="e.g., 12"
            min="1"
          />
        </div>

        {/* Housing Type */}
        <div className="space-y-3">
          <Label>Housing Type</Label>
          <Select value={housingType} onValueChange={setHousingType}>
            <SelectTrigger>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent className="pointer-events-auto bg-popover z-50">
              {HOUSING_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Furnished Status */}
        <div className="space-y-3">
          <Label>Furnished Status</Label>
          <Select value={furnishedStatus} onValueChange={setFurnishedStatus}>
            <SelectTrigger>
              <SelectValue placeholder="Select status" />
            </SelectTrigger>
            <SelectContent className="pointer-events-auto bg-popover z-50">
              {FURNISHED_STATUS.map((status) => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Deposit Range */}
        <div className="space-y-3">
          <Label>Deposit Range (€)</Label>
          <div className="pt-2">
            <Slider
              value={depositRange}
              onValueChange={(value) => setDepositRange(value as [number, number])}
              min={0}
              max={5000}
              step={100}
              className="mb-2"
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>€{depositRange[0]}</span>
              <span>€{depositRange[1]}</span>
            </div>
          </div>
        </div>

        {/* Service Costs Range */}
        <div className="space-y-3">
          <Label>Service Costs (€/month)</Label>
          <div className="pt-2">
            <Slider
              value={serviceCostsRange}
              onValueChange={(value) => setServiceCostsRange(value as [number, number])}
              min={0}
              max={500}
              step={10}
              className="mb-2"
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>€{serviceCostsRange[0]}</span>
              <span>€{serviceCostsRange[1]}</span>
            </div>
          </div>
        </div>

        {/* Available Date */}
        <div className="space-y-3">
          <Label>Available From</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className={cn(
                  "w-full justify-start text-left font-normal",
                  !availableDate && "text-muted-foreground"
                )}
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {availableDate ? format(availableDate, "PPP") : "Pick a date"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 pointer-events-auto bg-popover z-50" align="start">
              <Calendar
                mode="single"
                selected={availableDate}
                onSelect={setAvailableDate}
                initialFocus
                className="pointer-events-auto"
              />
            </PopoverContent>
          </Popover>
        </div>

        {/* Pets Allowed */}
        <div className="space-y-3 flex items-end">
          <div className="flex items-center space-x-2 pb-2">
            <Switch id="pets" checked={petsAllowed} onCheckedChange={setPetsAllowed} />
            <Label htmlFor="pets" className="cursor-pointer">
              Pets Allowed
            </Label>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t">
        <Button variant="outline" onClick={onCancel} className="smooth-hover">
          Cancel
        </Button>
        <Button onClick={handleGenerate} className="smooth-hover hover:scale-105">
          Generate Search
        </Button>
      </div>
    </div>
  );
};
