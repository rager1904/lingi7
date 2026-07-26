/**
 * TrackingTimeline — vertical timeline of shipment tracking events
 * Used on the public tracking page and order detail page.
 */

import React from "react";
import type { TrackingEvent, ShipmentStatus } from "../../types";
import { SHIPMENT_STATUS_LABEL, formatDateTime } from "../../utils";

interface Props {
  events: TrackingEvent[];
  currentStatus: ShipmentStatus;
}

const ORDERED_STATUSES: ShipmentStatus[] = [
  "CREATED",
  "DISPATCHED",
  "IN_TRANSIT",
  "CUSTOMS",
  "CLEARED",
  "DELIVERED",
];

export const TrackingTimeline: React.FC<Props> = ({ events, currentStatus }) => {
  const currentIndex = ORDERED_STATUSES.indexOf(currentStatus);

  return (
    <div className="space-y-0">
      {ORDERED_STATUSES.map((status, idx) => {
        const isCompleted = idx <= currentIndex;
        const isCurrent = idx === currentIndex;
        const matchingEvent = events.find((e) => e.status === status);

        return (
          <TimelineStep
            key={status}
            label={SHIPMENT_STATUS_LABEL[status]}
            isCompleted={isCompleted}
            isCurrent={isCurrent}
            isLast={idx === ORDERED_STATUSES.length - 1}
            event={matchingEvent}
          />
        );
      })}
    </div>
  );
};

interface StepProps {
  label: string;
  isCompleted: boolean;
  isCurrent: boolean;
  isLast: boolean;
  event?: TrackingEvent;
}

const TimelineStep: React.FC<StepProps> = ({
  label,
  isCompleted,
  isCurrent,
  isLast,
  event,
}) => (
  <div className="flex gap-4">
    {/* Connector column */}
    <div className="flex flex-col items-center">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
          isCompleted
            ? isCurrent
              ? "border-emerald-600 bg-emerald-600"
              : "border-emerald-500 bg-emerald-500"
            : "border-gray-300 bg-white"
        }`}
        aria-hidden="true"
      >
        {isCompleted ? (
          <CheckIcon className="h-4 w-4 text-white" />
        ) : (
          <span className="h-2 w-2 rounded-full bg-gray-300" />
        )}
      </div>
      {!isLast && (
        <div
          className={`mt-1 w-0.5 flex-1 ${
            isCompleted ? "bg-emerald-400" : "bg-gray-200"
          }`}
          style={{ minHeight: "2rem" }}
        />
      )}
    </div>

    {/* Content column */}
    <div className={`pb-6 ${isLast ? "pb-0" : ""}`}>
      <p
        className={`text-sm font-semibold ${
          isCurrent ? "text-emerald-700" : isCompleted ? "text-gray-800" : "text-gray-400"
        }`}
      >
        {label}
        {isCurrent && (
          <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
            Current
          </span>
        )}
      </p>
      {event && (
        <>
          <p className="mt-0.5 text-xs text-gray-500">{formatDateTime(event.timestamp)}</p>
          {event.location && (
            <p className="mt-0.5 text-xs text-gray-500">{event.location}</p>
          )}
          {event.description && (
            <p className="mt-1 text-sm text-gray-600">{event.description}</p>
          )}
        </>
      )}
    </div>
  </div>
);

const CheckIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 20 20"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
      clipRule="evenodd"
    />
  </svg>
);

export default TrackingTimeline;
