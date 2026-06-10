import { format, parseISO } from "date-fns";
import type { Slot } from "@/types";

interface Props {
  slots: Slot[];
  selected?: string;
  onSelect: (slot: Slot) => void;
}

export function SlotPicker({ slots, selected, onSelect }: Props) {
  if (slots.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic">No available slots for this day.</p>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
      {slots.map((slot) => {
        const isSelected = slot.start === selected;
        return (
          <button
            key={slot.start}
            onClick={() => onSelect(slot)}
            className={`text-sm px-3 py-2 rounded-lg border transition-colors ${
              isSelected
                ? "bg-brand-500 text-white border-brand-500"
                : "bg-white text-gray-700 border-gray-200 hover:border-brand-500 hover:text-brand-500"
            }`}
          >
            {format(parseISO(slot.start), "h:mm a")}
          </button>
        );
      })}
    </div>
  );
}
