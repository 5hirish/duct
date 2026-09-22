"use client"

import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/**
 * A stepped or continuous range. Keyboard: arrows move one `step`, Home and
 * End jump to the ends, Page Up/Down move ten. Give it an `aria-label` (or
 * `aria-labelledby`) — the thumb is the focusable part and has no text.
 *
 * `marks` draws a dot on the track at every step, which is how a stepped
 * slider says it is stepped without a row of words under it: the thumb
 * lands on a dot, and the dots the range has covered read as done. The
 * track grows to hold them.
 */
// Half of the thumb used with `marks` (size-5), for the dots' inset.
const THUMB_HALF = "0.625rem"

function Slider({
  className,
  defaultValue,
  value,
  min = 0,
  max = 100,
  step = 1,
  marks = false,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root> & { marks?: boolean }) {
  const values = React.useMemo(
    () =>
      Array.isArray(value)
        ? value
        : Array.isArray(defaultValue)
          ? defaultValue
          : [min],
    [value, defaultValue, min]
  )
  const stops = marks ? Math.floor((max - min) / step) + 1 : 0
  const covered = values[values.length - 1]

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      step={step}
      className={cn(
        "relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50",
        className
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className={cn(
          "relative w-full grow overflow-hidden rounded-full bg-muted",
          marks ? "h-4" : "h-1.5"
        )}
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="absolute h-full bg-primary"
        />
        {marks &&
          Array.from({ length: stops }, (_, i) => {
            const at = min + i * step
            return (
              <span
                key={at}
                aria-hidden
                data-slot="slider-mark"
                data-covered={at <= covered || undefined}
                className="absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-muted-foreground data-covered:bg-primary-foreground"
                // Radix keeps the thumb inside the track, so its centre runs
                // from half a thumb in to half a thumb short of the end; the
                // dots run the same span or the thumb misses the end ones.
                style={{ left: `calc(${THUMB_HALF} + (100% - 2 * ${THUMB_HALF}) * ${(at - min) / (max - min)})` }}
              />
            )
          })}
      </SliderPrimitive.Track>
      {values.map((_, index) => (
        <SliderPrimitive.Thumb
          data-slot="slider-thumb"
          key={index}
          className={cn(
            "block shrink-0 rounded-full border border-primary bg-background shadow-sm ring-ring/40 transition-[box-shadow] hover:ring-4 focus-visible:ring-4 focus-visible:outline-hidden disabled:pointer-events-none",
            marks ? "size-5" : "size-4"
          )}
        />
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }
