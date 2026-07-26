/**
 * EscrowStatusBadge — visual pill showing current escrow state
 * Used on order cards, order detail, checkout confirmation.
 */

import React from "react";
import type { EscrowStatus } from "../../types";
import {
  ESCROW_STATUS_LABEL,
  ESCROW_STATUS_COLOUR,
} from "../../utils";

interface Props {
  status: EscrowStatus;
  size?: "sm" | "md";
}

const COLOUR_CLASSES: Record<string, string> = {
  gray: "bg-gray-100 text-gray-700",
  yellow: "bg-yellow-100 text-yellow-800",
  blue: "bg-blue-100 text-blue-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
  orange: "bg-orange-100 text-orange-800",
};

export const EscrowStatusBadge: React.FC<Props> = ({ status, size = "md" }) => {
  const colour = ESCROW_STATUS_COLOUR[status];
  const label = ESCROW_STATUS_LABEL[status];
  const colourClass = COLOUR_CLASSES[colour] ?? COLOUR_CLASSES.gray;

  const sizeClass = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${sizeClass} ${colourClass}`}
      role="status"
      aria-label={`Escrow status: ${label}`}
    >
      <StatusDot colour={colour} />
      {label}
    </span>
  );
};

const StatusDot: React.FC<{ colour: string }> = ({ colour }) => {
  const dotClasses: Record<string, string> = {
    gray: "bg-gray-400",
    yellow: "bg-yellow-500 animate-pulse",
    blue: "bg-blue-500 animate-pulse",
    green: "bg-green-500",
    red: "bg-red-500 animate-pulse",
    orange: "bg-orange-500",
  };
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${dotClasses[colour] ?? dotClasses.gray}`}
    />
  );
};

export default EscrowStatusBadge;
