import { useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export const SLOTS = 11

/** The run arrows of the game's "Edit positioning" (formations: attackingdirection_<i> / defensivedirection_<i>, test
 * FD1): 0 = none; attacking 1 up, 2 up-right, 3 right, 4 down-right, 5 down; defending 1 up, 2 up-left, 3 left,
 * 4 down-left, 5 down (the pitch drawn as the game draws it: own goal on the left). [dx, dy] of each. */
export const ATTACK_RUNS: Record<number, [number, number]> = { 1: [0, -1], 2: [1, -1], 3: [1, 0], 4: [1, 1], 5: [0, 1] }
export const DEFENSE_RUNS: Record<number, [number, number]> = { 1: [0, -1], 2: [-1, -1], 3: [-1, 0], 4: [-1, 1], 5: [0, 1] }

/** The color the game gives a position on its formation pitch: goalkeeper, defenders, midfielders, attackers. */
export function positionColor(code: number | undefined) {
  if (code === undefined) return '#9ca3af'
  if (code === 0) return '#f97316'
  if (code <= 8) return '#eab308'
  if (code <= 19) return '#22c55e'
  return '#3b82f6'
}

const W = 300
const H = 200
const R = 8

const clamp = (v: number) => Math.round(Math.min(0.99, Math.max(0.01, v)) * 100) / 100

function Arrow({ x, y, run, dirs, dashed }: { x: number; y: number; run: number; dirs: Record<number, [number, number]>; dashed?: boolean }) {
  const d = dirs[run]
  if (!d) return null
  const len = Math.hypot(d[0], d[1])
  const [ux, uy] = [d[0] / len, d[1] / len]
  const [x1, y1] = [x + ux * (R + 1), y + uy * (R + 1)]
  const [x2, y2] = [x + ux * (R + 16), y + uy * (R + 16)]
  const head = (a: number) => `${x2 - 5 * (ux * Math.cos(a) - uy * Math.sin(a))},${y2 - 5 * (uy * Math.cos(a) + ux * Math.sin(a))}`
  return (
    <g stroke="white" fill="white" opacity={dashed ? 0.75 : 1} pointerEvents="none">
      <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={2} strokeDasharray={dashed ? '3 2' : undefined} />
      <polygon points={`${x2},${y2} ${head(0.5)} ${head(-0.5)}`} stroke="none" />
    </g>
  )
}

/** A formation on a pitch drawn like the game's (own goal on the left; offset y = depth, left to right; offset x = side,
 * top to bottom): one dot per slot in its position's color, with its attacking (solid) and defending (dashed) run
 * arrows. With `onMove`, a dot can be dragged (offsets 0.01-0.99). `selected` / `onSelect`: the slot picked. */
export function FormationPitch({
  columns,
  labels,
  selected,
  onSelect,
  onMove,
  className,
}: {
  columns: Record<string, number>
  labels?: string[]
  selected?: number | null
  onSelect?: (slot: number) => void
  onMove?: (slot: number, x: number, y: number) => void
  className?: string
}) {
  const svg = useRef<SVGSVGElement>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const at = (e: React.PointerEvent) => {
    const box = svg.current!.getBoundingClientRect()
    return { depth: clamp((e.clientX - box.left) / box.width), side: clamp((e.clientY - box.top) / box.height) }
  }
  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${W} ${H}`}
      className={cn('w-full touch-none select-none rounded-md', className)}
      onPointerMove={(e) => {
        if (dragging === null || !onMove) return
        const p = at(e)
        onMove(dragging, p.side, p.depth)
      }}
      onPointerUp={() => setDragging(null)}
      onPointerLeave={() => setDragging(null)}
    >
      <rect width={W} height={H} fill="#2f5d34" />
      {Array.from({ length: 6 }, (_, i) => (
        <rect key={i} x={i * 50} width={25} height={H} fill="#356a3b" />
      ))}
      <g stroke="rgba(255,255,255,0.55)" strokeWidth={1.2} fill="none">
        <rect x={2} y={2} width={W - 4} height={H - 4} />
        <line x1={W / 2} y1={2} x2={W / 2} y2={H - 2} />
        <circle cx={W / 2} cy={H / 2} r={24} />
        <rect x={2} y={H / 2 - 44} width={44} height={88} />
        <rect x={W - 46} y={H / 2 - 44} width={44} height={88} />
        <rect x={2} y={H / 2 - 18} width={14} height={36} />
        <rect x={W - 16} y={H / 2 - 18} width={14} height={36} />
      </g>
      {Array.from({ length: SLOTS }, (_, i) => {
        const x = (columns[`offset${i}y`] ?? 0.5) * W
        const y = (columns[`offset${i}x`] ?? 0.5) * H
        return (
          <g key={i}>
            <Arrow x={x} y={y} run={columns[`attackingdirection_${i}`] ?? 0} dirs={ATTACK_RUNS} />
            <Arrow x={x} y={y} run={columns[`defensivedirection_${i}`] ?? 0} dirs={DEFENSE_RUNS} dashed />
            <circle
              cx={x}
              cy={y}
              r={R}
              fill={positionColor(columns[`position${i}`])}
              stroke={selected === i ? 'white' : 'rgba(0,0,0,0.35)'}
              strokeWidth={selected === i ? 2.5 : 1}
              className={onMove ? 'cursor-grab active:cursor-grabbing' : onSelect ? 'cursor-pointer' : undefined}
              onPointerDown={(e) => {
                onSelect?.(i)
                if (!onMove) return
                ;(e.target as SVGElement).ownerSVGElement?.setPointerCapture(e.pointerId)
                setDragging(i)
              }}
            />
            {labels?.[i] && (
              <text x={x} y={y + R + 9} textAnchor="middle" fontSize={8} fill="white" pointerEvents="none" style={{ paintOrder: 'stroke' }} stroke="rgba(0,0,0,0.6)" strokeWidth={2}>
                {labels[i]}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
